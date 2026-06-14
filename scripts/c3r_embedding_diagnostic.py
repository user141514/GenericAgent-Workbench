"""Lightweight embedding substitution diagnostic for the C3R manuscript.

This script stress-tests whether a frozen fragment embedding content scalar can
replace hand-crafted FullContent features under a support-removed split.  It is
not the full BindingDB-hard matrix; it builds a local candidate-ranking proxy
from the available train/val/test positive split plus CA/context-matched decoys.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RDLogger.DisableLog("rdApp.*")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "temp" / "bindingdb_data"
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "embedding_diagnostic"

CONTENT_FEATURES = ["morgan", "bit_corr", "d_heavy", "d_rings", "d_mw", "d_logp", "d_tpsa"]
EMBED_FEATURES = ["embed_cosine", "embed_l1", "embed_l2", "embed_dot"]
QUERY_COLUMNS = ["old_fragment", "core_key", "attachment_signature", "endpoint", "target_key"]


@dataclass(frozen=True)
class QueryGroup:
    query_id: str
    old_fragment: str
    core_key: str
    attachment_signature: str
    endpoint: str
    target_key: str
    true_candidates: tuple[str, ...]
    true_clusters: tuple[str, ...]


class FragmentEmbedder:
    name = "base"

    def encode_many(self, smiles_list: list[str]) -> dict[str, np.ndarray]:
        raise NotImplementedError


class RdkitDescriptorEmbedder(FragmentEmbedder):
    name = "rdkit_descriptor"

    def encode_many(self, smiles_list: list[str]) -> dict[str, np.ndarray]:
        return {smi: rdkit_descriptor_vector(smi) for smi in smiles_list}


class ChemBertaEmbedder(FragmentEmbedder):
    name = "chemberta"

    def __init__(self, model_name: str, batch_size: int = 32, device: str = "auto") -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.device = torch.device(device)
        self.batch_size = batch_size
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.model_name = model_name

    def encode_many(self, smiles_list: list[str]) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        torch = self.torch
        for start in range(0, len(smiles_list), self.batch_size):
            batch_raw = smiles_list[start : start + self.batch_size]
            batch = [normalize_dummy_atoms(s) for s in batch_raw]
            encoded = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            with torch.no_grad():
                outputs = self.model(**encoded)
            hidden = outputs.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)
            pooled = pooled.detach().cpu().numpy().astype(np.float32)
            for smi, vec in zip(batch_raw, pooled):
                out[smi] = vec
        return out


def normalize_dummy_atoms(smiles: str) -> str:
    return re.sub(r"\[\d+\*\]", "[*]", str(smiles))


def safe_mol(smiles: str):
    return Chem.MolFromSmiles(str(smiles))


def fingerprint(smiles: str):
    mol = safe_mol(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)


def content_features(old_fragment: str, candidate_fragment: str) -> np.ndarray:
    mol_a = safe_mol(old_fragment)
    mol_b = safe_mol(candidate_fragment)
    fp_a = fingerprint(old_fragment)
    fp_b = fingerprint(candidate_fragment)
    if mol_a is None or mol_b is None or fp_a is None or fp_b is None:
        return np.zeros(len(CONTENT_FEATURES), dtype=np.float32)

    morgan = DataStructs.TanimotoSimilarity(fp_a, fp_b)
    arr_a = np.zeros((2048,), dtype=np.float32)
    arr_b = np.zeros((2048,), dtype=np.float32)
    DataStructs.ConvertToNumpyArray(fp_a, arr_a)
    DataStructs.ConvertToNumpyArray(fp_b, arr_b)
    if arr_a.std() > 0 and arr_b.std() > 0:
        bit_corr = float(np.corrcoef(arr_a, arr_b)[0, 1])
    else:
        bit_corr = 0.0
    if not math.isfinite(bit_corr):
        bit_corr = 0.0

    vals = [
        morgan,
        bit_corr,
        abs(mol_a.GetNumHeavyAtoms() - mol_b.GetNumHeavyAtoms()),
        abs(rdMolDescriptors.CalcNumRings(mol_a) - rdMolDescriptors.CalcNumRings(mol_b)),
        abs(Descriptors.MolWt(mol_a) - Descriptors.MolWt(mol_b)),
        abs(Descriptors.MolLogP(mol_a) - Descriptors.MolLogP(mol_b)),
        abs(Descriptors.TPSA(mol_a) - Descriptors.TPSA(mol_b)),
    ]
    return np.asarray(vals, dtype=np.float32)


def rdkit_descriptor_vector(smiles: str) -> np.ndarray:
    mol = safe_mol(smiles)
    if mol is None:
        return np.zeros(16, dtype=np.float32)
    vals = [
        mol.GetNumHeavyAtoms(),
        rdMolDescriptors.CalcNumRings(mol),
        rdMolDescriptors.CalcNumAromaticRings(mol),
        rdMolDescriptors.CalcNumAliphaticRings(mol),
        rdMolDescriptors.CalcNumHBA(mol),
        rdMolDescriptors.CalcNumHBD(mol),
        rdMolDescriptors.CalcNumRotatableBonds(mol),
        rdMolDescriptors.CalcFractionCSP3(mol),
        Descriptors.MolWt(mol),
        Descriptors.MolLogP(mol),
        Descriptors.TPSA(mol),
        Descriptors.NumValenceElectrons(mol),
        Descriptors.HeavyAtomMolWt(mol),
        Descriptors.NHOHCount(mol),
        Descriptors.NOCount(mol),
        Descriptors.NumHeteroatoms(mol),
    ]
    arr = np.asarray(vals, dtype=np.float32)
    arr[~np.isfinite(arr)] = 0.0
    return arr


def embedding_pair_features(old_fragment: str, candidate_fragment: str, vectors: dict[str, np.ndarray]) -> np.ndarray:
    a = vectors.get(old_fragment)
    b = vectors.get(candidate_fragment)
    if a is None or b is None:
        return np.zeros(len(EMBED_FEATURES), dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    cosine = float(np.dot(a, b) / denom) if denom > 0 else 0.0
    diff = a - b
    vals = [cosine, float(np.mean(np.abs(diff))), float(np.linalg.norm(diff)), float(np.dot(a, b))]
    return np.asarray(vals, dtype=np.float32)


def ca_score(content: np.ndarray) -> float:
    morgan = float(content[0])
    distance = float(content[2] + content[3] + content[4] + content[5])
    return 0.75 * morgan + 0.25 / (1.0 + distance)


def load_split(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = []
    for name in ["train.tsv", "val.tsv", "test.tsv"]:
        path = data_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing split file: {path}")
        frame = pd.read_csv(path, sep="\t")
        frame["split"] = name.removesuffix(".tsv")
        frames.append(frame)
    return frames[0], frames[1], frames[2]


def build_query_groups(frame: pd.DataFrame, limit: int = 0) -> list[QueryGroup]:
    groups: list[QueryGroup] = []
    grouped = frame.groupby(QUERY_COLUMNS, dropna=False, sort=False)
    for idx, (key, rows) in enumerate(grouped):
        if limit and idx >= limit:
            break
        old, core, att, endpoint, target = [str(x) for x in key]
        candidates = tuple(sorted(set(str(x) for x in rows["candidate_fragment"])))
        clusters = tuple(sorted(set(str(x) for x in rows["candidate_cluster"])))
        query_id = f"q{idx:06d}"
        groups.append(
            QueryGroup(
                query_id=query_id,
                old_fragment=old,
                core_key=core,
                attachment_signature=att,
                endpoint=endpoint,
                target_key=target,
                true_candidates=candidates,
                true_clusters=clusters,
            )
        )
    return groups


def build_candidate_pool(*frames: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    by_context: dict[tuple[str, str], set[str]] = {}
    for frame in frames:
        for row in frame.itertuples(index=False):
            key = (str(row.attachment_signature), str(row.endpoint))
            by_context.setdefault(key, set()).add(str(row.candidate_fragment))
    return {key: sorted(vals) for key, vals in by_context.items()}


def known_positive_map(*frames: pd.DataFrame) -> dict[tuple[str, str, str, str, str], set[str]]:
    mapping: dict[tuple[str, str, str, str, str], set[str]] = {}
    for frame in frames:
        for row in frame.itertuples(index=False):
            key = (
                str(row.old_fragment),
                str(row.core_key),
                str(row.attachment_signature),
                str(row.endpoint),
                str(row.target_key),
            )
            mapping.setdefault(key, set()).add(str(row.candidate_fragment))
    return mapping


def candidates_for_query(
    query: QueryGroup,
    pool: dict[tuple[str, str], list[str]],
    positives: dict[tuple[str, str, str, str, str], set[str]],
    rng: np.random.Generator,
    max_decoys: int,
) -> tuple[list[str], set[str]]:
    key = (query.attachment_signature, query.endpoint)
    query_key = (
        query.old_fragment,
        query.core_key,
        query.attachment_signature,
        query.endpoint,
        query.target_key,
    )
    true_set = set(query.true_candidates)
    known_true = positives.get(query_key, set())
    raw_decoys = [c for c in pool.get(key, []) if c not in known_true]
    if max_decoys > 0 and len(raw_decoys) > max_decoys:
        raw_decoys = list(rng.choice(raw_decoys, size=max_decoys, replace=False))
    candidates = sorted(set(raw_decoys) | true_set)
    return candidates, true_set


def make_pair_table(
    groups: list[QueryGroup],
    pool: dict[tuple[str, str], list[str]],
    positives: dict[tuple[str, str, str, str, str], set[str]],
    max_decoys: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for query in groups:
        candidates, true_set = candidates_for_query(query, pool, positives, rng, max_decoys)
        for candidate in candidates:
            rows.append(
                {
                    "query_id": query.query_id,
                    "old_fragment": query.old_fragment,
                    "candidate_fragment": candidate,
                    "attachment_signature": query.attachment_signature,
                    "endpoint": query.endpoint,
                    "target_key": query.target_key,
                    "label": 1 if candidate in true_set else 0,
                }
            )
    return pd.DataFrame(rows)


def featurize_pairs(
    pairs: pd.DataFrame,
    vectors: dict[str, np.ndarray],
    include_context: bool = False,
) -> dict[str, np.ndarray]:
    full_rows = []
    embed_rows = []
    ca_vals = []
    for row in pairs.itertuples(index=False):
        full = content_features(str(row.old_fragment), str(row.candidate_fragment))
        embed = embedding_pair_features(str(row.old_fragment), str(row.candidate_fragment), vectors)
        full_rows.append(full)
        embed_rows.append(embed)
        ca_vals.append(ca_score(full))
    full_x = np.vstack(full_rows).astype(np.float32)
    embed_x = np.vstack(embed_rows).astype(np.float32)
    features = {
        "FullContent": full_x,
        "EmbedContent": embed_x,
        "Full+EmbedContent": np.hstack([full_x, embed_x]).astype(np.float32),
    }
    if include_context:
        buckets = np.digitize(np.asarray(ca_vals), bins=np.asarray([0.2, 0.4, 0.6, 0.8]), right=False)
        bucket_onehot = np.eye(5, dtype=np.float32)[buckets]
        interactions = np.hstack([full_x * bucket_onehot[:, [i]] for i in range(5)])
        features["ContextFullContent"] = np.hstack([full_x, interactions]).astype(np.float32)
    return features


def fit_models(train_features: dict[str, np.ndarray], y: np.ndarray) -> dict[str, object]:
    models = {}
    for name, x in train_features.items():
        if len(set(y.tolist())) < 2:
            raise ValueError("Training labels must include positive and negative rows.")
        clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced", solver="lbfgs"),
        )
        clf.fit(x, y)
        models[name] = clf
    return models


def evaluate_scores(pairs: pd.DataFrame, scores: np.ndarray) -> dict[str, float]:
    work = pairs[["query_id", "old_fragment", "label"]].copy()
    work["score"] = scores
    mrrs = []
    hits1 = []
    hits10 = []
    ndcg10s = []
    by_old: dict[str, list[float]] = {}
    for query_id, group in work.groupby("query_id", sort=False):
        ranked = group.sort_values("score", ascending=False).reset_index(drop=True)
        labels = ranked["label"].to_numpy()
        pos = np.flatnonzero(labels == 1)
        if len(pos) == 0:
            continue
        rank = int(pos[0]) + 1
        rr = 1.0 / rank
        mrrs.append(rr)
        hits1.append(1.0 if rank <= 1 else 0.0)
        hits10.append(1.0 if rank <= 10 else 0.0)
        gains = labels[:10].astype(float)
        discounts = 1.0 / np.log2(np.arange(2, len(gains) + 2))
        dcg = float(np.sum(gains * discounts))
        ideal_count = min(int(labels.sum()), 10)
        ideal = float(np.sum(discounts[:ideal_count])) if ideal_count else 0.0
        ndcg = dcg / ideal if ideal > 0 else 0.0
        ndcg10s.append(ndcg)
        old_fragment = str(group["old_fragment"].iloc[0])
        by_old.setdefault(old_fragment, []).append(rr)

    of_macro_mrr = float(np.mean([np.mean(vals) for vals in by_old.values()])) if by_old else 0.0
    return {
        "queries": int(len(mrrs)),
        "MRR": float(np.mean(mrrs)) if mrrs else 0.0,
        "Hit@1": float(np.mean(hits1)) if hits1 else 0.0,
        "Hit@10": float(np.mean(hits10)) if hits10 else 0.0,
        "NDCG@10": float(np.mean(ndcg10s)) if ndcg10s else 0.0,
        "OF-macro-MRR": of_macro_mrr,
    }


def unique_fragments(*frames: pd.DataFrame) -> list[str]:
    vals: set[str] = set()
    for frame in frames:
        vals.update(str(x) for x in frame["old_fragment"])
        vals.update(str(x) for x in frame["candidate_fragment"])
    return sorted(vals)


def write_report(path: Path, results: dict, args: argparse.Namespace) -> None:
    lines = [
        "# C3R Embedding Substitution Diagnostic",
        "",
        "## Scope",
        "",
        "This is a lightweight support-removed diagnostic, not the full BindingDB-hard 5.4M-row matrix.",
        "It tests whether replacing hand-crafted content features with frozen fragment embeddings removes the need for context-calibrated content ranking.",
        "",
        "## Configuration",
        "",
        f"- data_dir: `{args.data_dir}`",
        f"- embedding_backend: `{args.embedding_backend}`",
        f"- chemberta_model: `{args.chemberta_model}`",
        f"- max_train_queries: `{args.max_train_queries}`",
        f"- max_test_queries: `{args.max_test_queries}`",
        f"- max_decoys_per_query: `{args.max_decoys_per_query}`",
        f"- seed: `{args.seed}`",
        "",
        "## Metrics",
        "",
        "| Model | MRR | Hit@1 | Hit@10 | NDCG@10 | OF-macro-MRR | Queries |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in results["metrics"].items():
        lines.append(
            "| {name} | {MRR:.4f} | {Hit1:.4f} | {Hit10:.4f} | {NDCG:.4f} | {OF:.4f} | {Q} |".format(
                name=name,
                MRR=metrics["MRR"],
                Hit1=metrics["Hit@1"],
                Hit10=metrics["Hit@10"],
                NDCG=metrics["NDCG@10"],
                OF=metrics["OF-macro-MRR"],
                Q=metrics["queries"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation Gate",
            "",
            "- If EmbedContent <= FullContent, the frozen embedding does not replace the existing content scalar in this diagnostic.",
            "- If Full+EmbedContent improves but remains below ContextFullContent, embeddings add content signal but do not remove the context-calibration claim.",
            "- If EmbedContent or Full+EmbedContent approaches/exceeds ContextFullContent, the manuscript should narrow the C3R claim and report the embedding stress test.",
            "",
            "## Caveat",
            "",
            "The current local split files contain positive rows only; this script builds CA/context-matched decoys from the candidate pool as a diagnostic proxy.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a C3R embedding substitution diagnostic.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--embedding-backend", choices=["rdkit_descriptor", "chemberta"], default="rdkit_descriptor")
    parser.add_argument("--chemberta-model", default="seyonec/ChemBERTa-zinc-base-v1")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-train-queries", type=int, default=0)
    parser.add_argument("--max-test-queries", type=int, default=0)
    parser.add_argument("--max-decoys-per-query", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train, val, test = load_split(args.data_dir)
    audit = {
        "train_rows": int(len(train)),
        "val_rows": int(len(val)),
        "test_rows": int(len(test)),
        "train_label_counts": train["label"].value_counts().to_dict(),
        "val_label_counts": val["label"].value_counts().to_dict(),
        "test_label_counts": test["label"].value_counts().to_dict(),
    }
    if set(train["label"].unique()) != {1} or set(test["label"].unique()) != {1}:
        raise ValueError("This diagnostic expects the current local split format: positive rows only.")

    train_groups = build_query_groups(pd.concat([train, val], ignore_index=True), args.max_train_queries)
    test_groups = build_query_groups(test, args.max_test_queries)
    pool = build_candidate_pool(train, val, test)
    positives = known_positive_map(train, val, test)
    train_pairs = make_pair_table(train_groups, pool, positives, args.max_decoys_per_query, args.seed)
    test_pairs = make_pair_table(test_groups, pool, positives, args.max_decoys_per_query, args.seed + 1)
    audit.update(
        {
            "train_queries": len(train_groups),
            "test_queries": len(test_groups),
            "train_pairs": int(len(train_pairs)),
            "test_pairs": int(len(test_pairs)),
            "train_pair_labels": train_pairs["label"].value_counts().to_dict(),
            "test_pair_labels": test_pairs["label"].value_counts().to_dict(),
        }
    )

    fragments = unique_fragments(train_pairs, test_pairs)
    if args.embedding_backend == "chemberta":
        embedder: FragmentEmbedder = ChemBertaEmbedder(args.chemberta_model, args.batch_size, args.device)
    else:
        embedder = RdkitDescriptorEmbedder()
    vectors = embedder.encode_many(fragments)

    train_features = featurize_pairs(train_pairs, vectors, include_context=True)
    test_features = featurize_pairs(test_pairs, vectors, include_context=True)
    y_train = train_pairs["label"].to_numpy(dtype=int)
    models = fit_models(train_features, y_train)
    metrics = {}
    for name, model in models.items():
        scores = model.predict_proba(test_features[name])[:, 1]
        metrics[name] = evaluate_scores(test_pairs, scores)

    result = {
        "audit": audit,
        "embedding_backend": args.embedding_backend,
        "embedding_model": args.chemberta_model if args.embedding_backend == "chemberta" else embedder.name,
        "metrics": metrics,
    }
    json_path = args.output_dir / f"embedding_diagnostic_{args.embedding_backend}.json"
    md_path = args.output_dir / f"embedding_diagnostic_{args.embedding_backend}.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(md_path, result, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"[written] {json_path}")
    print(f"[written] {md_path}")


if __name__ == "__main__":
    main()
