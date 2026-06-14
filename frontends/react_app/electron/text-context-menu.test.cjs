const path = require("node:path");

const helperPaths = [
  path.join(__dirname, "text-context-menu.cjs"),
  path.resolve(__dirname, "..", "..", "..", "packages", "gagent-desktop", "electron", "text-context-menu.cjs"),
];

describe("Electron text context menu", () => {
  for (const helperPath of helperPaths) {
    it(`builds editing roles for ${path.basename(path.dirname(helperPath))}`, () => {
      const { createTextEditingMenuTemplate, shouldShowTextEditingMenu } = require(helperPath);

      expect(shouldShowTextEditingMenu({ isEditable: true })).toBe(true);
      expect(shouldShowTextEditingMenu({ isEditable: false })).toBe(false);

      const template = createTextEditingMenuTemplate({
        editFlags: {
          canUndo: true,
          canRedo: false,
          canCut: true,
          canCopy: true,
          canPaste: true,
          canSelectAll: true,
        },
      });

      expect(template.map((item) => item.type || item.role)).toEqual([
        "undo",
        "redo",
        "separator",
        "cut",
        "copy",
        "paste",
        "separator",
        "selectAll",
      ]);
      expect(template.find((item) => item.role === "redo").enabled).toBe(false);
      expect(template.find((item) => item.role === "paste").enabled).toBe(true);
    });
  }
});
