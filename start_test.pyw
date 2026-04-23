# start_test.pyw - OpenAI Agents Backend 启动器 (webview窗口)
import webview, threading, subprocess, sys, time, os, ctypes, atexit, socket, random

# 设置后端
os.environ['GA_AGENT_BACKEND'] = 'openai-agents'

from core.runtime_env import preferred_python

WINDOW_WIDTH, WINDOW_HEIGHT, RIGHT_PADDING, TOP_PADDING = 600, 900, 0, 100

script_dir = os.path.dirname(os.path.abspath(__file__))
frontends_dir = os.path.join(script_dir, "frontends")
RUNTIME_PYTHON = preferred_python("rag-env")

def find_free_port(lo=18501, hi=18599):
    ports = list(range(lo, hi+1)); random.shuffle(ports)
    for p in ports:
        try: s = socket.socket(); s.bind(('127.0.0.1', p)); s.close(); return p
        except OSError: continue
    raise RuntimeError(f'No free port in {lo}-{hi}')

def get_screen_width():
    try: return ctypes.windll.user32.GetSystemMetrics(0)
    except: return 1920

def start_streamlit(port):
    global proc
    cmd = [RUNTIME_PYTHON, "-m", "streamlit", "run", os.path.join(frontends_dir, "stapp.py"), 
           "--server.port", str(port), "--server.address", "localhost", "--server.headless", "true"]
    proc = subprocess.Popen(cmd)
    atexit.register(proc.kill)

def inject(text):
    window.evaluate_js(f"""
        const textarea = document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (textarea) {{
            const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            nativeTextAreaValueSetter.call(textarea, {repr(text)});
            textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
            textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
            setTimeout(() => {{
                const btn = document.querySelector('[data-testid="stChatInputSubmitButton"]');
                if (btn) {{btn.click();console.log('Submitted:', {repr(text)});}}
            }}, 200);
        }}""")

def get_last_reply_time():
    last = window.evaluate_js("""
        const el = document.getElementById('last-reply-time');
        el ? parseInt(el.textContent) : 0;
    """) or 0
    return last or int(time.time())

def idle_monitor():
    last_trigger_time = 0
    while True:
        time.sleep(5)
        try:
            now = time.time()
            if now - last_trigger_time < 120: continue
            last_reply = get_last_reply_time()
            if now - last_reply > 1800:
                print('[Idle Monitor] Detected idle state, injecting task...')
                inject("[AUTO]用户已经离开超过30分钟，作为自主智能体，请阅读自动化sop，执行自动任务。")
                last_trigger_time = now
        except Exception as e:
            print(f'[Idle Monitor] Error: {e}')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--llm_no', type=int, default=0, help='LLM编号')
    args = parser.parse_args()
    
    port = find_free_port()
    print(f'[Launch] Using port {port}')
    threading.Thread(target=start_streamlit, args=(port,), daemon=True).start()
    
    # 启动空闲监控
    monitor_thread = threading.Thread(target=idle_monitor, daemon=True)
    monitor_thread.start()
    
    if os.name == 'nt':
        screen_width = get_screen_width()
        x_pos = screen_width - WINDOW_WIDTH - RIGHT_PADDING
    else: x_pos = 100
    
    time.sleep(2)
    
    window = webview.create_window(
        title='GenericAgent (OpenAI Agents)', url=f'http://localhost:{port}',
        width=WINDOW_WIDTH, height=WINDOW_HEIGHT, x=x_pos, y=TOP_PADDING,
        resizable=True, text_select=True)
    webview.start()
