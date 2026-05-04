"""Desktop Pet with Skin System — Cross-platform with True Transparency"""
import os, re, sys, json, threading, io
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageDraw, ImageFont, ImageOps

PORT = 41983
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SKINS_DIR = os.path.join(SCRIPT_DIR, 'skins')

class SkinLoader:
    """Load and parse skin configuration"""
    @staticmethod
    def load_skin(skin_path):
        """Load skin.json and return skin config"""
        config_file = os.path.join(skin_path, 'skin.json')
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"skin.json not found in {skin_path}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if 'animations' not in config:
            raise ValueError("skin.json must contain 'animations' field")

        config['path'] = skin_path
        return config

    @staticmethod
    def list_skins():
        """List all available skins"""
        if not os.path.exists(SKINS_DIR):
            return []

        skins = []
        for item in os.listdir(SKINS_DIR):
            skin_path = os.path.join(SKINS_DIR, item)
            if os.path.isdir(skin_path):
                config_file = os.path.join(skin_path, 'skin.json')
                if os.path.exists(config_file):
                    skins.append(item)
        return skins

class AnimationLoader:
    """Load animation frames from sprite sheet"""
    @staticmethod
    def load_sprite_frames(skin_path, anim_config):
        """Load frames from sprite sheet"""
        file_path = os.path.join(skin_path, anim_config['file'])
        sprite_config = anim_config['sprite']

        img = Image.open(file_path)
        frames = []

        frame_width = sprite_config['frameWidth']
        frame_height = sprite_config['frameHeight']
        frame_count = sprite_config['frameCount']
        columns = sprite_config['columns']
        start_frame = sprite_config.get('startFrame', 0)

        for i in range(frame_count):
            frame_idx = start_frame + i
            row = frame_idx // columns
            col = frame_idx % columns

            x = col * frame_width
            y = row * frame_height

            frame = img.crop((x, y, x + frame_width, y + frame_height))
            frames.append(frame)

        return frames


def _load_default_font(size):
    """Load a usable font for bubble text."""
    font_candidates = [
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/arial.ttf',
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _normalize_bubble_text(text):
    """Normalize text for fonts that cannot render some symbols."""
    text = (text or '').strip()
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines:
        turn_match = re.match(r'^\s*🔄?\s*Turn\s+(\d+)\s*$', lines[0], flags=re.IGNORECASE)
        if turn_match:
            rest = '\n'.join(line.strip() for line in lines[1:] if line.strip())
            return f"Turn {turn_match.group(1)}: {rest}" if rest else f"Turn {turn_match.group(1)}:"
    return text.replace('🔄 Turn', 'Turn').replace('🔄', '').strip()


def _wrap_text_for_width(draw, text, font, max_width):
    """Wrap text to fit inside max_width."""
    text = _normalize_bubble_text(text)
    if not text:
        return ['']

    paragraphs = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    lines = []

    for paragraph in paragraphs:
        if not paragraph:
            lines.append('')
            continue

        current = ''
        for ch in paragraph:
            candidate = current + ch
            bbox = draw.textbbox((0, 0), candidate, font=font)
            width = bbox[2] - bbox[0]
            if current and width > max_width:
                lines.append(current)
                current = ch
            else:
                current = candidate
        if current:
            lines.append(current)

    return lines or ['']


def build_bubble_image(message, max_width=220):
    """Build a PIL image for the toast bubble using the user asset when available."""
    message = (message or '').strip()
    bubble_path = next((p for p in [os.path.join(SCRIPT_DIR, 'chat_bubble.png'),
                                     os.path.join(SCRIPT_DIR, 'bubble.png')]
                        if os.path.exists(p)), None)

    if bubble_path:
        bubble = Image.open(bubble_path).convert('RGBA')
    else:
        bubble = Image.new('RGBA', (256, 128), (255, 255, 255, 0))
        draw = ImageDraw.Draw(bubble)
        draw.rounded_rectangle((8, 8, 247, 87), radius=12, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
        draw.polygon([(48, 87), (72, 87), (56, 112)], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))

    bubble = ImageOps.contain(bubble, (max_width, max(64, int(max_width * bubble.height / bubble.width))), Image.NEAREST)

    # Detect the actual opaque bubble region to position text correctly
    alpha = bubble.getchannel('A')
    content_box = alpha.getbbox()  # (left, top, right, bottom) of opaque area
    if content_box:
        cb_left, cb_top, cb_right, cb_bottom = content_box
    else:
        cb_left, cb_top, cb_right, cb_bottom = 0, 0, bubble.width, bubble.height
    content_w = cb_right - cb_left
    content_h = cb_bottom - cb_top

    font_size = max(12, content_h // 6)
    font = _load_default_font(font_size)
    draw = ImageDraw.Draw(bubble)

    # Padding relative to the opaque bubble region, not the full image
    inner_pad_x = max(6, content_w // 14)
    inner_pad_top = max(4, content_h // 12)
    inner_pad_bottom = max(12, content_h // 4)
    text_area_width = max(36, content_w - inner_pad_x * 2)

    lines = _wrap_text_for_width(draw, message, font, text_area_width)
    ascent, descent = font.getmetrics() if hasattr(font, 'getmetrics') else (font_size, font_size // 4)
    line_height = max(font_size, ascent + descent)
    usable_h = content_h - inner_pad_top - inner_pad_bottom
    max_lines = max(1, usable_h // line_height)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            last = lines[-1]
            while last and draw.textbbox((0, 0), last + '…', font=font)[2] > text_area_width:
                last = last[:-1]
            lines[-1] = (last + '…') if last else '…'

    total_text_height = len(lines) * line_height
    y = cb_top + inner_pad_top + max(0, (usable_h - total_text_height) // 2) - 3

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = cb_left + inner_pad_x + (text_area_width - text_width) / 2
        draw.text((x, y), line, font=font, fill=(32, 32, 32, 255))
        y += line_height

    alpha = bubble.getchannel('A')
    bbox = alpha.getbbox()
    if bbox:
        bubble = bubble.crop(bbox)

    width, height = bubble.size
    alpha = bubble.getchannel('A')
    bottom_y = height - 1
    tail_x = width // 2
    for y in range(height - 1, -1, -1):
        xs = [x for x in range(width) if alpha.getpixel((x, y)) > 0]
        if xs:
            bottom_y = y
            tail_x = xs[len(xs) // 2]
            break

    return {
        'image': bubble,
        'size': bubble.size,
        'tail_tip': (tail_x, bottom_y),
    }


def build_notification_image(title, summary, max_width=340):
    """Build a cartoon-style notification dialog with action buttons.

    Returns dict with image, size, tail_tip, and hit-test rects for buttons.
    """
    title = (title or '').strip()
    summary = (summary or '').strip()

    # ── Fonts ──
    title_font = _load_default_font(18)
    body_font = _load_default_font(14)
    btn_font = _load_default_font(15)

    # ── Measure text ──
    draw_dummy = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    text_area_w = max_width - 48  # left/right padding

    title_lines = _wrap_text_for_width(draw_dummy, title, title_font, text_area_w)
    summary_lines = _wrap_text_for_width(draw_dummy, summary, body_font, text_area_w)

    title_h = max(24, len(title_lines) * 28)
    summary_h = max(20, len(summary_lines) * 22)
    btn_h = 44
    tail_h = 18
    shadow_offset = 5

    # ── Calculate canvas size ──
    content_h = 28 + title_h + 12 + summary_h + 20 + btn_h + 20
    canvas_w = max_width + shadow_offset * 2
    canvas_h = content_h + tail_h + shadow_offset * 2

    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    sx, sy = shadow_offset, shadow_offset  # shadow-aware origin
    body_w = max_width
    body_h = content_h

    # ── Colours ──
    bg_color = (255, 248, 231, 255)        # cream
    border_color = (93, 64, 55, 255)       # dark brown
    title_color = (61, 43, 31, 255)        # deep brown
    summary_color = (78, 78, 78, 255)      # dark grey
    btn_bg = (255, 140, 66, 255)           # orange
    btn_text = (255, 255, 255, 255)        # white
    close_bg = (180, 160, 150, 255)        # muted brown
    shadow_color = (0, 0, 0, 40)

    # ── Shadow ──
    shadow_rect = (sx + 4, sy + 4, sx + body_w + 4, sy + body_h + 4)
    draw.rounded_rectangle(shadow_rect, radius=16, fill=shadow_color)

    # ── Main body ──
    body_rect = (sx, sy, sx + body_w, sy + body_h)
    draw.rounded_rectangle(body_rect, radius=16, fill=bg_color, outline=border_color, width=4)

    # ── Separator line under title ──
    sep_y = sy + 26 + title_h
    draw.line([(sx + 20, sep_y), (sx + body_w - 20, sep_y)], fill=border_color, width=1)

    # ── Title text ──
    y = sy + 16
    for line in title_lines:
        bbox = draw_dummy.textbbox((0, 0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        x = sx + (body_w - tw) / 2
        draw.text((x, y), line, font=title_font, fill=title_color)
        y += 28

    # ── Close button area (top-right circle) ──
    close_cx = sx + body_w - 24
    close_cy = sy + 20
    close_r = 10
    draw.ellipse(
        (close_cx - close_r, close_cy - close_r, close_cx + close_r, close_cy + close_r),
        fill=close_bg,
    )
    # × mark
    cross_sz = 5
    draw.line(
        (close_cx - cross_sz, close_cy - cross_sz, close_cx + cross_sz, close_cy + cross_sz),
        fill=(255, 255, 255, 255), width=2,
    )
    draw.line(
        (close_cx + cross_sz, close_cy - cross_sz, close_cx - cross_sz, close_cy + cross_sz),
        fill=(255, 255, 255, 255), width=2,
    )

    # ── Summary text ──
    y = sep_y + 12
    for line in summary_lines:
        bbox = draw_dummy.textbbox((0, 0), line, font=body_font)
        tw = bbox[2] - bbox[0]
        x = sx + (body_w - tw) / 2
        draw.text((x, y), line, font=body_font, fill=summary_color)
        y += 22

    # ── "查看结果" button ──
    btn_w = 160
    btn_h = 44
    btn_x = sx + (body_w - btn_w) / 2
    btn_y = sy + body_h - btn_h - 16
    btn_rect = (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h)

    draw.rounded_rectangle(btn_rect, radius=10, fill=btn_bg)
    btn_label = "查看结果 →"
    bbox = draw_dummy.textbbox((0, 0), btn_label, font=btn_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (btn_x + (btn_w - tw) / 2, btn_y + (btn_h - th) / 2 - 1),
        btn_label, font=btn_font, fill=btn_text,
    )

    # ── Tail triangle (pointing down toward pet) ──
    tail_cx = sx + int(body_w * 0.75)
    tail_top = sy + body_h
    tail_bottom = tail_top + tail_h
    tail_half = 10
    draw.polygon(
        [(tail_cx - tail_half, tail_top), (tail_cx + tail_half, tail_top), (tail_cx, tail_bottom)],
        fill=bg_color, outline=border_color, width=2,
    )

    # ── Compute hit-test rects in image coordinates ──
    close_btn_rect = (close_cx - 16, close_cy - 16, close_cx + 16, close_cy + 16)

    return {
        'image': img,
        'size': img.size,
        'tail_tip': (tail_cx, tail_bottom),
        'view_btn_rect': btn_rect,
        'close_btn_rect': close_btn_rect,
    }


def _notify_qtapp_show():
    """Tell the QtApp (if running) to show its chat panel."""
    try:
        from urllib.request import urlopen
        urlopen("http://127.0.0.1:41984/show", timeout=2)
    except Exception:
        pass  # QtApp not running — silently ignore


# ============================================================================
# Shared Base Class
# ============================================================================
class PetBase:
    """Shared logic for Mac and Windows pet implementations."""

    def _schedule_main(self, fn):
        """Schedule fn on the GUI main thread. Subclasses must override."""
        raise NotImplementedError

    def set_state_safe(self, state):
        """Thread-safe wrapper for set_state."""
        self._schedule_main(lambda: self.set_state(state))

    def show_toast_safe(self, message):
        """Thread-safe wrapper for show_toast."""
        self._schedule_main(lambda m=message: self.show_toast(m))

    def _start_server(self):
        """Start HTTP control server."""
        pet = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)

                if 'state' in params:
                    state = params['state'][0]
                    pet.set_state_safe(state)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                elif 'notify' in params:
                    raw = params['notify'][0]
                    parts = raw.split('|', 1)
                    title = parts[0]
                    summary = parts[1] if len(parts) > 1 else ''
                    pet.show_notification_safe(title, summary)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                elif 'notify_dismiss' in params:
                    pet._schedule_main(pet._dismiss_notification)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                elif 'msg' in params:
                    msg = params['msg'][0]
                    pet.show_toast_safe(msg)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(
                        b'?state=idle/walk/run/sprint | ?msg=hello | ?notify=title|summary | ?notify_dismiss'
                    )

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
                if body:
                    pet.show_toast_safe(body)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'ok')
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'empty body')

            def log_message(self, *a):
                pass

        try:
            HTTPServer.allow_reuse_address = True
            srv = HTTPServer(('127.0.0.1', PORT), Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            print(f'✓ Server: http://127.0.0.1:{PORT}/?state=walk')
        except OSError as e:
            if e.errno == 48:
                print(f'⚠ Port {PORT} already in use')
            else:
                raise


# ============================================================================
# macOS Implementation - Pure Cocoa with True Transparency
# ============================================================================
if sys.platform == 'darwin':
    from Cocoa import (
        NSApplication, NSWindow, NSImageView, NSImage, NSData, NSTimer,
        NSMenu, NSMenuItem, NSApp, NSFloatingWindowLevel, NSColor,
        NSBackingStoreBuffered, NSWindowStyleMaskBorderless,
        NSApplicationActivationPolicyAccessory
    )
    from Foundation import NSMakeRect, NSMakePoint, NSMakeSize
    from PyObjCTools import AppHelper
    import objc

    class MacPet(PetBase):
        def __init__(self, skin_name=None):
            self.app = NSApplication.sharedApplication()
            self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

            # Load skin
            self.load_skin(skin_name)
            self.available_skins = SkinLoader.list_skins()

            # Get screen size
            from AppKit import NSScreen, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary
            screen = NSScreen.mainScreen()
            screen_frame = screen.frame()
            screen_width = screen_frame.size.width
            screen_height = screen_frame.size.height

            # Position at right side
            x_pos = screen_width - 200
            y_pos = 300

            # Create transparent window
            self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x_pos, y_pos, self.display_width, self.display_height),
                NSWindowStyleMaskBorderless,
                NSBackingStoreBuffered,
                False
            )

            self.window.setOpaque_(False)
            self.window.setBackgroundColor_(NSColor.clearColor())
            self.window.setLevel_(NSFloatingWindowLevel)
            self.window.setMovableByWindowBackground_(True)
            self.window.setAcceptsMouseMovedEvents_(True)

            # Make window sticky across spaces (stays in fixed screen position)
            self.window.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorStationary
            )

            # Create custom view for handling mouse events
            from AppKit import NSView
            from objc import super as objc_super

            class DraggableImageView(NSView):
                """Custom view that handles dragging and double-click"""
                def initWithFrame_(self, frame):
                    self = objc_super(DraggableImageView, self).initWithFrame_(frame)
                    if self is None:
                        return None
                    self.image_view = NSImageView.alloc().initWithFrame_(self.bounds())
                    self.image_view.setImageScaling_(1)  # NSImageScaleProportionallyUpOrDown
                    self.addSubview_(self.image_view)

                    # Create overlay view for toast (always on top)
                    # Make it non-opaque so it doesn't block the image
                    self.overlay_view = NSView.alloc().initWithFrame_(self.bounds())
                    self.overlay_view.setWantsLayer_(True)
                    self.addSubview_(self.overlay_view)

                    self.drag_start = None
                    return self

                def mouseDown_(self, event):
                    """Handle mouse down for dragging"""
                    if event.clickCount() == 2:
                        # Double-click to quit
                        from AppKit import NSApp
                        NSApp.terminate_(None)
                    else:
                        # Start dragging
                        self.drag_start = event.locationInWindow()

                def mouseDragged_(self, event):
                    """Handle mouse drag"""
                    if self.drag_start:
                        current_location = event.locationInWindow()
                        window_frame = self.window().frame()

                        dx = current_location.x - self.drag_start.x
                        dy = current_location.y - self.drag_start.y

                        new_origin = NSMakePoint(
                            window_frame.origin.x + dx,
                            window_frame.origin.y + dy
                        )

                        self.window().setFrameOrigin_(new_origin)

                def acceptsFirstMouse_(self, event):
                    """Accept first mouse click"""
                    return True

                def rightMouseDown_(self, event):
                    from AppKit import NSMenu, NSMenuItem, NSApp

                    menu = NSMenu.alloc().init()
                    pet = self.window().delegate()  # Assuming the window’s delegate is MacPet instance

                    for skin_name in pet.available_skins:  # preload this in MacPet.__init__
                        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                            skin_name,
                            'changeSkin:',
                            ''
                        )
                        item.setTarget_(pet)
                        item.setRepresentedObject_(skin_name)
                        menu.addItem_(item)

                    menu.addItem_(NSMenuItem.separatorItem())
                    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Quit', 'terminate:', '')
                    menu.addItem_(quit_item)

                    NSApp.activateIgnoringOtherApps_(True)
                    NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

            # Create draggable view
            self.content_view = DraggableImageView.alloc().initWithFrame_(
                NSMakeRect(0, 0, self.display_width, self.display_height)
            )
            self.image_view = self.content_view.image_view
            self.overlay_view = self.content_view.overlay_view
            self.window.setContentView_(self.content_view)

            # Animation state
            self.current_state = 'idle'
            self.frame_idx = 0

            # Toast state
            self.toast_label = None
            self.toast_timer = None
            self.toast_image = None
            self.toast_window = None

            # Start animation timer
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / self.animations[self.current_state]['fps'],
                self,
                'animate:',
                None,
                True
            )

            # Show window
            self.window.makeKeyAndOrderFront_(None)

            # Start HTTP server
            self._start_server()

            print(f"✓ macOS Pet started at ({x_pos}, {y_pos})")
            print(f"  Animations: {', '.join(self.animations.keys())}")

        def load_skin(self, skin_name=None):
            """Load skin configuration and animations"""
            available_skins = SkinLoader.list_skins()
            if not available_skins:
                raise FileNotFoundError(f"No skins found in {SKINS_DIR}")

            if skin_name is None or skin_name not in available_skins:
                skin_name = available_skins[0]

            skin_path = os.path.join(SKINS_DIR, skin_name)
            self.skin_config = SkinLoader.load_skin(skin_path)

            # Get display size
            display_size = self.skin_config.get('size', {})
            self.display_width = display_size.get('width', 128)
            self.display_height = display_size.get('height', 128)

            # Load animations
            self.animations = {}
            for anim_name, anim_config in self.skin_config['animations'].items():
                pil_frames = AnimationLoader.load_sprite_frames(skin_path, anim_config)

                # Scale frames
                scaled_frames = []
                for frame in pil_frames:
                    if frame.mode != 'RGBA':
                        frame = frame.convert('RGBA')
                    scaled = frame.resize((self.display_width, self.display_height), Image.NEAREST)
                    scaled_frames.append(scaled)

                # Convert to NSImage with proper alpha handling
                ns_images = []
                for pil_img in scaled_frames:
                    # Convert PIL to PNG bytes (PNG preserves alpha channel)
                    png_buffer = io.BytesIO()
                    pil_img.save(png_buffer, format='PNG')
                    png_data = png_buffer.getvalue()

                    # Create NSImage from PNG data
                    ns_data = NSData.dataWithBytes_length_(png_data, len(png_data))
                    ns_image = NSImage.alloc().initWithData_(ns_data)
                    ns_images.append(ns_image)

                self.animations[anim_name] = {
                    'frames': ns_images,
                    'fps': anim_config.get('sprite', {}).get('fps', 6)
                }

        def animate_(self, timer):
            """Animation callback"""
            anim = self.animations[self.current_state]
            frames = anim['frames']

            if frames:
                self.image_view.setImage_(frames[self.frame_idx])
                self.frame_idx = (self.frame_idx + 1) % len(frames)

        def set_state(self, state):
            """Change animation state (must be called on main thread)"""
            if state in self.animations and state != self.current_state:
                self.current_state = state
                self.frame_idx = 0

                # Update timer interval
                self.timer.invalidate()
                self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    1.0 / self.animations[self.current_state]['fps'],
                    self,
                    'animate:',
                    None,
                    True
                )
                print(f"→ State: {state}")

        def _schedule_main(self, fn):
            AppHelper.callAfter(fn)

        def show_toast(self, message):
            """Show toast message above pet"""
            from AppKit import NSImageView

            if self.toast_window:
                self.toast_window.orderOut_(None)
                self.toast_window = None
                self.toast_label = None
            if self.toast_timer:
                self.toast_timer.invalidate()
                self.toast_timer = None

            bubble_info = build_bubble_image(message, max_width=max(180, min(260, self.display_width * 2)))
            bubble_pil = bubble_info['image']
            bubble_width, bubble_height = bubble_info['size']
            tail_x, tail_y = bubble_info['tail_tip']

            png_buffer = io.BytesIO()
            bubble_pil.save(png_buffer, format='PNG')
            png_data = png_buffer.getvalue()
            ns_data = NSData.dataWithBytes_length_(png_data, len(png_data))
            self.toast_image = NSImage.alloc().initWithData_(ns_data)

            pet_frame = self.window.frame()
            anchor_x = pet_frame.origin.x + self.display_width * 0.75
            anchor_y = pet_frame.origin.y + self.display_height * 1.65
            toast_x = anchor_x - tail_x
            toast_y = anchor_y - tail_y

            self.toast_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(toast_x, toast_y, bubble_width, bubble_height),
                NSWindowStyleMaskBorderless,
                NSBackingStoreBuffered,
                False
            )
            self.toast_window.setOpaque_(False)
            self.toast_window.setBackgroundColor_(NSColor.clearColor())
            self.toast_window.setLevel_(NSFloatingWindowLevel)
            self.toast_window.setIgnoresMouseEvents_(True)
            self.toast_window.setHasShadow_(False)

            self.toast_label = NSImageView.alloc().initWithFrame_(
                NSMakeRect(0, 0, bubble_width, bubble_height)
            )
            self.toast_label.setImage_(self.toast_image)
            self.toast_label.setImageScaling_(0)
            self.toast_window.setContentView_(self.toast_label)
            self.toast_window.orderFrontRegardless()

            self.toast_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3.0,
                self,
                'hideToast:',
                None,
                False
            )
            print(f"Toast: {message}")

        def hideToast_(self, timer):
            """Hide toast message"""
            if self.toast_window:
                self.toast_window.orderOut_(None)
                self.toast_window = None
            self.toast_label = None
            self.toast_image = None
            self.toast_timer = None

        def run(self):
            """Run the application"""
            AppHelper.runEventLoop()
        
        def changeSkin_(self, sender):
            skin_name = sender.representedObject()
            print(f"Changing skin to: {skin_name}")
            self.load_skin(skin_name)
            self.current_state = 'idle'
            self.frame_idx = 0

# ============================================================================
# Windows Implementation - tkinter with transparentcolor
# ============================================================================
else:
    import tkinter as tk
    from PIL import ImageTk

    class WinPet(PetBase):
        def __init__(self, skin_name=None):
            self.root = tk.Tk()
            self.root.wm_attributes('-topmost', True)

            # Load skin
            self.load_skin(skin_name)

            # Setup window
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()

            x_pos = screen_width - 200
            y_pos = screen_height - 300

            self.root.geometry(f'{self.display_width}x{self.display_height}+{x_pos}+{y_pos}')
            self.root.overrideredirect(True)
            self.root.wm_attributes('-topmost', True)

            # Transparent background
            self.root.wm_attributes('-transparentcolor', '#F0F0F0')
            self.root.config(bg='#F0F0F0')

            # Create label
            self.label = tk.Label(self.root, bg='#F0F0F0', bd=0)
            self.label.pack()

            # Bind events
            self.label.bind('<Button-1>', lambda e: setattr(self, '_d', (e.x, e.y)))
            self.label.bind('<B1-Motion>', self._drag)
            self.label.bind('<Double-1>', lambda e: (self.root.destroy(), os._exit(0)))
            self.label.bind('<Button-3>', self._on_right_click)

            # Animation state
            self.current_state = 'idle'
            self.frame_idx = 0

            # Toast state
            self.toast_window = None
            self.toast_photo = None

            # Notification state
            self.notif_window = None
            self.notif_photo = None
            self.notif_hit_rects = {}

            # Start animation
            self._animate()
            self._start_server()

            print(f"✓ Windows Pet started at ({x_pos}, {y_pos})")
            print(f"  Animations: {', '.join(self.animations.keys())}")

            self.root.mainloop()

        def load_skin(self, skin_name=None):
            """Load skin configuration and animations"""
            available_skins = SkinLoader.list_skins()
            if not available_skins:
                raise FileNotFoundError(f"No skins found in {SKINS_DIR}")

            if skin_name is None or skin_name not in available_skins:
                skin_name = available_skins[0]

            skin_path = os.path.join(SKINS_DIR, skin_name)
            self.skin_config = SkinLoader.load_skin(skin_path)

            # Get display size
            display_size = self.skin_config.get('size', {})
            self.display_width = display_size.get('width', 128)
            self.display_height = display_size.get('height', 128)

            # Load animations
            self.animations = {}
            for anim_name, anim_config in self.skin_config['animations'].items():
                pil_frames = AnimationLoader.load_sprite_frames(skin_path, anim_config)

                # Scale and convert frames
                tk_frames = []
                for frame in pil_frames:
                    if frame.mode != 'RGBA':
                        frame = frame.convert('RGBA')
                    scaled = frame.resize((self.display_width, self.display_height), Image.NEAREST)
                    tk_frames.append(ImageTk.PhotoImage(scaled))

                self.animations[anim_name] = {
                    'frames': tk_frames,
                    'fps': anim_config.get('sprite', {}).get('fps', 6)
                }

        def set_state(self, state):
            """Change animation state"""
            if state in self.animations and state != self.current_state:
                self.current_state = state
                self.frame_idx = 0
                print(f"→ State: {state}")

        def _drag(self, e):
            x = self.root.winfo_x() + e.x - self._d[0]
            y = self.root.winfo_y() + e.y - self._d[1]
            self.root.geometry(f'+{x}+{y}')

        def _animate(self):
            """Animate current state"""
            if self.current_state not in self.animations:
                self.root.after(100, self._animate)
                return

            anim = self.animations[self.current_state]
            frames = anim['frames']

            if frames:
                self.label.config(image=frames[self.frame_idx])
                self.frame_idx = (self.frame_idx + 1) % len(frames)

            delay = int(1000 / anim['fps'])
            self.root.after(delay, self._animate)

        def show_toast(self, message):
            """Show toast message above pet"""
            if self.toast_window:
                try:
                    self.toast_window.destroy()
                except:
                    pass
                self.toast_window = None

            bubble_info = build_bubble_image(message, max_width=max(180, min(260, self.display_width * 2)))
            bubble_pil = bubble_info['image']
            bubble_width, bubble_height = bubble_info['size']
            tail_x, tail_y = bubble_info['tail_tip']

            self.toast_photo = ImageTk.PhotoImage(bubble_pil)

            self.toast_window = tk.Toplevel(self.root)
            self.toast_window.overrideredirect(True)
            self.toast_window.wm_attributes('-topmost', True)
            self.toast_window.wm_attributes('-transparentcolor', '#00ff01')
            self.toast_window.config(bg='#00ff01')

            toast_label = tk.Label(
                self.toast_window,
                image=self.toast_photo,
                bg='#00ff01',
                bd=0,
                highlightthickness=0
            )
            toast_label.pack()

            pet_x = self.root.winfo_x()
            pet_y = self.root.winfo_y()
            anchor_x = pet_x + int(self.display_width * 0.75)
            anchor_y = pet_y
            toast_x = anchor_x - tail_x
            toast_y = anchor_y - bubble_height

            self.toast_window.geometry(f'{bubble_width}x{bubble_height}+{toast_x}+{toast_y}')

            self.root.after(3000, self._hide_toast)
            print(f"Toast: {message}")

        def _hide_toast(self):
            """Hide toast message"""
            if self.toast_window:
                try:
                    self.toast_window.destroy()
                    self.toast_window = None
                except:
                    pass

        def _dismiss_notification(self):
            """Dismiss the notification window."""
            if self.notif_window:
                try:
                    self.notif_window.destroy()
                    self.notif_window = None
                except:
                    pass

        def _pet_jump(self):
            """Brief hop animation — move pet window up then back down."""
            try:
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                # Jump up
                self.root.geometry(f'+{x}+{y - 20}')
                self.root.update_idletasks()
                # Fall back after 120ms
                self.root.after(120, lambda: self.root.geometry(f'+{x}+{y}'))
            except Exception:
                pass

        def show_notification(self, title, summary):
            """Show a cartoon notification dialog above the pet.

            Stays visible until the user clicks an action button or dismisses it.
            """
            # Dismiss any existing notification first
            self._dismiss_notification()

            notif_info = build_notification_image(title, summary)
            notif_pil = notif_info['image']
            notif_w, notif_h = notif_info['size']
            tail_x, tail_y = notif_info['tail_tip']
            self.notif_hit_rects = {
                'view': notif_info['view_btn_rect'],
                'close': notif_info['close_btn_rect'],
            }

            self.notif_photo = ImageTk.PhotoImage(notif_pil)

            self.notif_window = tk.Toplevel(self.root)
            self.notif_window.overrideredirect(True)
            self.notif_window.wm_attributes('-topmost', True)
            self.notif_window.wm_attributes('-transparentcolor', '#00ff01')
            self.notif_window.config(bg='#00ff01')

            notif_label = tk.Label(
                self.notif_window,
                image=self.notif_photo,
                bg='#00ff01',
                bd=0,
                highlightthickness=0,
            )
            notif_label.pack()

            # Position: tail tip anchors to pet's upper-centre
            pet_x = self.root.winfo_x()
            pet_y = self.root.winfo_y()
            anchor_x = pet_x + int(self.display_width * 0.75)
            anchor_y = pet_y
            notif_x = anchor_x - tail_x
            notif_y = anchor_y - notif_h

            # Keep on screen
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            notif_x = max(0, min(notif_x, screen_w - notif_w))
            notif_y = max(0, notif_y)

            self.notif_window.geometry(f'{notif_w}x{notif_h}+{notif_x}+{notif_y}')

            # Click handler — check which button area was hit
            def _on_click(e):
                vr = self.notif_hit_rects.get('view', (0, 0, 0, 0))
                cr = self.notif_hit_rects.get('close', (0, 0, 0, 0))
                if vr[0] <= e.x <= vr[2] and vr[1] <= e.y <= vr[3]:
                    # "查看结果" clicked → notify QtApp then dismiss
                    self._dismiss_notification()
                    threading.Thread(
                        target=lambda: _notify_qtapp_show(),
                        daemon=True,
                    ).start()
                elif cr[0] <= e.x <= cr[2] and cr[1] <= e.y <= cr[3]:
                    self._dismiss_notification()

            notif_label.bind('<Button-1>', _on_click)
            self.notif_window.bind('<Button-1>', _on_click)

            # Pet jump animation
            self._pet_jump()

        def show_notification_safe(self, title, summary):
            """Thread-safe wrapper for show_notification."""
            self._schedule_main(lambda t=title, s=summary: self.show_notification(t, s))

        def _schedule_main(self, fn):
            self.root.after(0, fn)

        def run(self):
            """Run the application (already in mainloop)"""
            pass
        
        def _on_right_click(self, event):
            # Build a dynamic menu of all available skins
            menu = tk.Menu(self.root, tearoff=0)
            for skin_name in SkinLoader.list_skins():
                menu.add_command(
                    label=skin_name,
                    command=lambda name=skin_name: self._change_skin(name)
                )
            menu.add_separator()
            menu.add_command(label="Quit", command=lambda: (self.root.destroy(), os._exit(0)))
            menu.tk_popup(event.x_root, event.y_root)

        def _change_skin(self, skin_name):
            print(f"Changing skin to: {skin_name}")
            self.load_skin(skin_name)
            self.current_state = 'idle'
            self.frame_idx = 0

if __name__ == '__main__':
    # Singleton: if port already in use, another instance is running
    import socket
    _s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _s.connect(('127.0.0.1', PORT))
        _s.close()
        print(f'⚠ Pet already running on port {PORT}, exiting.')
        sys.exit(0)
    except ConnectionRefusedError:
        pass

    if sys.platform == 'darwin':
        pet = MacPet('vita')
        pet.run()
    else:
        pet = WinPet('vita')
