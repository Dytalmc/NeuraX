import requests
from pathlib import Path
from PyQt6.QtGui import QImage, QColor, QPainter
from PyQt6.QtCore import QThread, pyqtSignal, QRect, Qt
import base64
import json

def create_default_steve_texture() -> QImage:
    """Generates a complete standard 64x64 default Steve skin texture if offline or no skin file is set."""
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    
    skin = QColor(198, 138, 100)
    skin_dark = QColor(180, 120, 90)
    hair = QColor(70, 45, 20)
    eye_w = QColor(255, 255, 255)
    eye_b = QColor(60, 60, 180)
    mouth = QColor(130, 80, 60)
    cyan = QColor(0, 160, 180)
    cyan_dark = QColor(0, 140, 160)
    blue = QColor(40, 50, 120)
    blue_dark = QColor(30, 40, 100)

    # --- HEAD (0..32, 0..16) ---
    painter.fillRect(8, 0, 8, 8, hair)          # Top
    painter.fillRect(16, 0, 8, 8, skin)         # Bottom
    painter.fillRect(0, 8, 8, 8, skin)          # Right side
    painter.fillRect(0, 8, 8, 2, hair)
    painter.fillRect(8, 8, 8, 8, skin)          # Front
    painter.fillRect(8, 8, 8, 2, hair)
    painter.fillRect(9, 12, 2, 1, eye_w)       # Right eye
    painter.fillRect(10, 12, 1, 1, eye_b)
    painter.fillRect(13, 12, 2, 1, eye_w)      # Left eye
    painter.fillRect(13, 12, 1, 1, eye_b)
    painter.fillRect(11, 14, 2, 1, mouth)       # Mouth
    painter.fillRect(16, 8, 8, 8, skin)         # Left side
    painter.fillRect(16, 8, 8, 2, hair)
    painter.fillRect(24, 8, 8, 8, skin)         # Back side
    painter.fillRect(24, 8, 8, 3, hair)         # Hair back

    # --- TORSO (16..40, 16..32) ---
    painter.fillRect(20, 16, 8, 4, cyan)        # Top
    painter.fillRect(28, 16, 8, 4, cyan)        # Bottom
    painter.fillRect(16, 20, 4, 12, cyan)       # Right side
    painter.fillRect(20, 20, 8, 12, cyan)       # Front
    painter.fillRect(28, 20, 4, 12, cyan)       # Left side
    painter.fillRect(32, 20, 8, 12, cyan_dark)  # Back

    # --- RIGHT ARM (40..56, 16..32) ---
    painter.fillRect(44, 16, 4, 4, cyan)        # Top
    painter.fillRect(48, 16, 4, 4, skin)        # Bottom
    painter.fillRect(40, 20, 4, 4, cyan)        # Outer top
    painter.fillRect(40, 24, 4, 8, skin)        # Outer bottom
    painter.fillRect(44, 20, 4, 4, cyan)        # Front top
    painter.fillRect(44, 24, 4, 8, skin)        # Front bottom
    painter.fillRect(48, 20, 4, 4, cyan)        # Inner top
    painter.fillRect(48, 24, 4, 8, skin)        # Inner bottom
    painter.fillRect(52, 20, 4, 4, cyan_dark)   # Back top
    painter.fillRect(52, 24, 4, 8, skin_dark)   # Back bottom

    # --- LEFT ARM (32..48, 48..64) ---
    painter.fillRect(36, 48, 4, 4, cyan)        # Top
    painter.fillRect(40, 48, 4, 4, skin)        # Bottom
    painter.fillRect(32, 52, 4, 4, cyan)        # Inner top
    painter.fillRect(32, 56, 4, 8, skin)        # Inner bottom
    painter.fillRect(36, 52, 4, 4, cyan)        # Front top
    painter.fillRect(36, 56, 4, 8, skin)        # Front bottom
    painter.fillRect(40, 52, 4, 4, cyan)        # Outer top
    painter.fillRect(40, 56, 4, 8, skin)        # Outer bottom
    painter.fillRect(44, 52, 4, 4, cyan_dark)   # Back top
    painter.fillRect(44, 56, 4, 8, skin_dark)   # Back bottom

    # --- RIGHT LEG (0..16, 16..32) ---
    painter.fillRect(4, 16, 4, 4, blue)         # Top
    painter.fillRect(8, 16, 4, 4, blue)         # Bottom
    painter.fillRect(0, 20, 4, 12, blue)        # Outer
    painter.fillRect(4, 20, 4, 12, blue)        # Front
    painter.fillRect(8, 20, 4, 12, blue)        # Inner
    painter.fillRect(12, 20, 4, 12, blue_dark)  # Back

    # --- LEFT LEG (16..32, 48..64) ---
    painter.fillRect(20, 48, 4, 4, blue)        # Top
    painter.fillRect(24, 48, 4, 4, blue)        # Bottom
    painter.fillRect(16, 52, 4, 12, blue)       # Inner
    painter.fillRect(20, 52, 4, 12, blue)       # Front
    painter.fillRect(24, 52, 4, 12, blue)       # Outer
    painter.fillRect(28, 52, 4, 12, blue_dark)  # Back

    painter.end()
    return img

def convert_legacy_skin_to_64x64(skin_img: QImage) -> QImage:
    if skin_img.height() == 64:
        return skin_img
    out = QImage(64, 64, QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))
    painter = QPainter(out)
    painter.drawImage(0, 0, skin_img)

    right_leg = skin_img.copy(QRect(0, 16, 16, 16))
    left_leg = right_leg.mirrored(True, False)
    painter.drawImage(16, 48, left_leg)

    right_arm = skin_img.copy(QRect(40, 16, 16, 16))
    left_arm = right_arm.mirrored(True, False)
    painter.drawImage(32, 48, left_arm)

    painter.end()
    return out

def is_skin_slim(skin_img: QImage) -> bool:
    if skin_img.height() == 32:
        return False
    if skin_img.format() != QImage.Format.Format_ARGB32:
        skin_img = skin_img.convertToFormat(QImage.Format.Format_ARGB32)
    
    transparent_count = 0
    total_checks = 0
    for y in range(20, 32):
        for x in (54, 55):
            pixel = skin_img.pixelColor(x, y)
            total_checks += 1
            if pixel.alpha() == 0:
                transparent_count += 1
    
    return (transparent_count / max(total_checks, 1)) > 0.5

def ensure_skin_model(skin_img: QImage, target_model: str) -> QImage:
    if skin_img.isNull():
        return skin_img
    if skin_img.format() != QImage.Format.Format_ARGB32:
        skin_img = skin_img.convertToFormat(QImage.Format.Format_ARGB32)

    skin_img = convert_legacy_skin_to_64x64(skin_img)
    currently_slim = is_skin_slim(skin_img)
    want_slim = (target_model.lower() == "slim")

    if currently_slim == want_slim:
        return skin_img

    out = skin_img.copy()
    painter = QPainter(out)

    def remap_face(src_rect: QRect, dst_rect: QRect, col_map: list):
        part = skin_img.copy(src_rect)
        w_src = src_rect.width()
        h_src = src_rect.height()
        w_dst = dst_rect.width()
        mapped = QImage(w_dst, h_src, QImage.Format.Format_ARGB32)
        mapped.fill(QColor(0, 0, 0, 0))
        for x_out, x_in in enumerate(col_map):
            if x_in < w_src and x_out < w_dst:
                for y in range(h_src):
                    mapped.setPixelColor(x_out, y, part.pixelColor(x_in, y))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(dst_rect, mapped)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    if want_slim:
        col_map = [0, 1, 2]
        remap_face(QRect(44, 16, 4, 4), QRect(44, 16, 3, 4), col_map)
        remap_face(QRect(48, 16, 4, 4), QRect(47, 16, 3, 4), col_map)
        remap_face(QRect(40, 20, 4, 12), QRect(40, 20, 3, 12), col_map)
        remap_face(QRect(44, 20, 4, 12), QRect(43, 20, 3, 12), col_map)
        remap_face(QRect(48, 20, 4, 12), QRect(46, 20, 3, 12), col_map)
        remap_face(QRect(52, 20, 4, 12), QRect(49, 20, 3, 12), col_map)

        remap_face(QRect(44, 32, 4, 4), QRect(44, 32, 3, 4), col_map)
        remap_face(QRect(48, 32, 4, 4), QRect(47, 32, 3, 4), col_map)
        remap_face(QRect(40, 36, 4, 12), QRect(40, 36, 3, 12), col_map)
        remap_face(QRect(44, 36, 4, 12), QRect(43, 36, 3, 12), col_map)
        remap_face(QRect(48, 36, 4, 12), QRect(46, 36, 3, 12), col_map)
        remap_face(QRect(52, 36, 4, 12), QRect(49, 36, 3, 12), col_map)

        remap_face(QRect(36, 48, 4, 4), QRect(36, 48, 3, 4), col_map)
        remap_face(QRect(40, 48, 4, 4), QRect(39, 48, 3, 4), col_map)
        remap_face(QRect(32, 52, 4, 12), QRect(32, 52, 3, 12), col_map)
        remap_face(QRect(36, 52, 4, 12), QRect(35, 52, 3, 12), col_map)
        remap_face(QRect(40, 52, 4, 12), QRect(38, 52, 3, 12), col_map)
        remap_face(QRect(44, 52, 4, 12), QRect(41, 52, 3, 12), col_map)

        remap_face(QRect(52, 48, 4, 4), QRect(52, 48, 3, 4), col_map)
        remap_face(QRect(56, 48, 4, 4), QRect(55, 48, 3, 4), col_map)
        remap_face(QRect(48, 52, 4, 12), QRect(48, 52, 3, 12), col_map)
        remap_face(QRect(52, 52, 4, 12), QRect(51, 52, 3, 12), col_map)
        remap_face(QRect(56, 52, 4, 12), QRect(54, 52, 3, 12), col_map)
        remap_face(QRect(60, 52, 4, 12), QRect(57, 52, 3, 12), col_map)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(52, 16, 4, 16, QColor(0, 0, 0, 0))
        painter.fillRect(52, 32, 4, 16, QColor(0, 0, 0, 0))
        painter.fillRect(44, 48, 4, 16, QColor(0, 0, 0, 0))
        painter.fillRect(60, 48, 4, 16, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    else:
        col_map = [0, 1, 2, 2]
        remap_face(QRect(44, 16, 3, 4), QRect(44, 16, 4, 4), col_map)
        remap_face(QRect(47, 16, 3, 4), QRect(48, 16, 4, 4), col_map)
        remap_face(QRect(40, 20, 3, 12), QRect(40, 20, 4, 12), col_map)
        remap_face(QRect(43, 20, 3, 12), QRect(44, 20, 4, 12), col_map)
        remap_face(QRect(46, 20, 3, 12), QRect(48, 20, 4, 12), col_map)
        remap_face(QRect(49, 20, 3, 12), QRect(52, 20, 4, 12), col_map)

        remap_face(QRect(44, 32, 3, 4), QRect(44, 32, 4, 4), col_map)
        remap_face(QRect(47, 32, 3, 4), QRect(48, 32, 4, 4), col_map)
        remap_face(QRect(40, 36, 3, 12), QRect(40, 36, 4, 12), col_map)
        remap_face(QRect(43, 36, 3, 12), QRect(44, 36, 4, 12), col_map)
        remap_face(QRect(46, 36, 3, 12), QRect(48, 36, 4, 12), col_map)
        remap_face(QRect(49, 36, 3, 12), QRect(52, 36, 4, 12), col_map)

        remap_face(QRect(36, 48, 3, 4), QRect(36, 48, 4, 4), col_map)
        remap_face(QRect(39, 48, 3, 4), QRect(40, 48, 4, 4), col_map)
        remap_face(QRect(32, 52, 3, 12), QRect(32, 52, 4, 12), col_map)
        remap_face(QRect(35, 52, 3, 12), QRect(36, 52, 4, 12), col_map)
        remap_face(QRect(38, 52, 3, 12), QRect(40, 52, 4, 12), col_map)
        remap_face(QRect(41, 52, 3, 12), QRect(44, 52, 4, 12), col_map)

        remap_face(QRect(52, 48, 3, 4), QRect(52, 48, 4, 4), col_map)
        remap_face(QRect(55, 48, 3, 4), QRect(56, 48, 4, 4), col_map)
        remap_face(QRect(48, 52, 3, 12), QRect(48, 52, 4, 12), col_map)
        remap_face(QRect(51, 52, 3, 12), QRect(52, 52, 4, 12), col_map)
        remap_face(QRect(54, 52, 3, 12), QRect(56, 52, 4, 12), col_map)
        remap_face(QRect(57, 52, 3, 12), QRect(60, 52, 4, 12), col_map)

    painter.end()
    return out

def render_skin_model(skin_img: QImage, model: str = "classic", second_layer: bool = True, view: str = "both", cape_img: QImage = None) -> QImage:
    """Renders 2D character composite model (Front & Back views) with Classic/Slim hands, 2nd Layer overlay toggles, and official Mojang Cape overlay."""
    if skin_img.isNull():
        skin_img = create_default_steve_texture()

    skin_img = ensure_skin_model(skin_img, model)

    if skin_img.format() != QImage.Format.Format_ARGB32:
        skin_img = skin_img.convertToFormat(QImage.Format.Format_ARGB32)

    is_legacy = (skin_img.height() == 32)
    is_slim = (model.lower() == "slim")
    arm_w = 3 if is_slim else 4

    r_arm_front_x = 43 if is_slim else 44
    l_arm_front_x = 35 if is_slim else 36
    r_arm_back_x = 49 if is_slim else 52
    l_arm_back_x = 41 if is_slim else 44

    r_arm_ov_front_x = 43 if is_slim else 44
    l_arm_ov_front_x = 51 if is_slim else 52
    r_arm_ov_back_x = 49 if is_slim else 52
    l_arm_ov_back_x = 57 if is_slim else 60

    if view == "both":
        canvas_w, canvas_h = 36, 32
        front_ox, back_ox = 0, 20
    elif view == "back":
        canvas_w, canvas_h = 16, 32
        front_ox, back_ox = -100, 0
    else:
        canvas_w, canvas_h = 16, 32
        front_ox, back_ox = 0, -100

    out = QImage(canvas_w, canvas_h, QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))

    painter = QPainter(out)

    def draw_part(src_rect: QRect, target_rect: QRect, mirror_h: bool = False):
        if src_rect.x() + src_rect.width() > skin_img.width() or src_rect.y() + src_rect.height() > skin_img.height():
            return
        part = skin_img.copy(src_rect)
        if mirror_h:
            part = part.mirrored(True, False)
        painter.drawImage(target_rect, part)

    # --- FRONT VIEW ---
    if front_ox >= 0:
        fox = front_ox
        arm_left_x = fox + (4 - arm_w)
        arm_right_x = fox + 12

        # Base Layers
        draw_part(QRect(8, 8, 8, 8), QRect(fox + 4, 0, 8, 8))
        draw_part(QRect(20, 20, 8, 12), QRect(fox + 4, 8, 8, 12))
        draw_part(QRect(r_arm_front_x, 20, arm_w, 12), QRect(arm_left_x, 8, arm_w, 12))
        if not is_legacy:
            draw_part(QRect(l_arm_front_x, 52, arm_w, 12), QRect(arm_right_x, 8, arm_w, 12))
        else:
            draw_part(QRect(r_arm_front_x, 20, arm_w, 12), QRect(arm_right_x, 8, arm_w, 12), mirror_h=True)
        draw_part(QRect(4, 20, 4, 12), QRect(fox + 4, 20, 4, 12))
        if not is_legacy:
            draw_part(QRect(20, 52, 4, 12), QRect(fox + 8, 20, 4, 12))
        else:
            draw_part(QRect(4, 20, 4, 12), QRect(fox + 8, 20, 4, 12), mirror_h=True)

        # Second Layer Overlays
        if second_layer:
            draw_part(QRect(40, 8, 8, 8), QRect(fox + 4, 0, 8, 8))
            if not is_legacy:
                draw_part(QRect(20, 36, 8, 12), QRect(fox + 4, 8, 8, 12))
                draw_part(QRect(r_arm_ov_front_x, 36, arm_w, 12), QRect(arm_left_x, 8, arm_w, 12))
                draw_part(QRect(l_arm_ov_front_x, 52, arm_w, 12), QRect(arm_right_x, 8, arm_w, 12))
                draw_part(QRect(4, 36, 4, 12), QRect(fox + 4, 20, 4, 12))
                draw_part(QRect(4, 52, 4, 12), QRect(fox + 8, 20, 4, 12))

    # --- BACK VIEW ---
    if back_ox >= 0:
        box = back_ox
        b_arm_left_x = box + (4 - arm_w)
        b_arm_right_x = box + 12

        # Base Layers
        draw_part(QRect(24, 8, 8, 8), QRect(box + 4, 0, 8, 8))
        draw_part(QRect(32, 20, 8, 12), QRect(box + 4, 8, 8, 12))
        if not is_legacy:
            draw_part(QRect(l_arm_back_x, 52, arm_w, 12), QRect(b_arm_left_x, 8, arm_w, 12))
        else:
            draw_part(QRect(r_arm_back_x, 20, arm_w, 12), QRect(b_arm_left_x, 8, arm_w, 12), mirror_h=True)
        draw_part(QRect(r_arm_back_x, 20, arm_w, 12), QRect(b_arm_right_x, 8, arm_w, 12))
        if not is_legacy:
            draw_part(QRect(28, 52, 4, 12), QRect(box + 4, 20, 4, 12))
        else:
            draw_part(QRect(12, 20, 4, 12), QRect(box + 4, 20, 4, 12), mirror_h=True)
        draw_part(QRect(12, 20, 4, 12), QRect(box + 8, 20, 4, 12))

        # Second Layer Overlays
        if second_layer:
            draw_part(QRect(56, 8, 8, 8), QRect(box + 4, 0, 8, 8))
            if not is_legacy:
                draw_part(QRect(32, 36, 8, 12), QRect(box + 4, 8, 8, 12))
                draw_part(QRect(l_arm_ov_back_x, 52, arm_w, 12), QRect(b_arm_left_x, 8, arm_w, 12))
                draw_part(QRect(r_arm_ov_back_x, 36, arm_w, 12), QRect(b_arm_right_x, 8, arm_w, 12))
                draw_part(QRect(12, 52, 4, 12), QRect(box + 4, 20, 4, 12))
                draw_part(QRect(12, 36, 4, 12), QRect(box + 8, 20, 4, 12))

        # Render Official Mojang Cape on Back Face
        if cape_img and not cape_img.isNull():
            cw = cape_img.width()
            ch = cape_img.height()
            scale_x = cw / 64.0
            scale_y = ch / 32.0
            src_x = int(12 * scale_x)
            src_y = int(1 * scale_y)
            src_w = int(10 * scale_x)
            src_h = int(16 * scale_y)
            cape_part = cape_img.copy(QRect(src_x, src_y, src_w, src_h))
            painter.drawImage(QRect(box + 3, 8, 10, 16), cape_part)

    painter.end()
    return out

class SkinDownloader(QThread):
    loaded = pyqtSignal(QImage)

    def __init__(
        self,
        uuid_str: str,
        cache_dir: Path,
        custom_skin_path: str = "",
        model: str = "classic",
        second_layer: bool = True,
        view_mode: str = "front",
        auth_mode: str = "microsoft",
        username: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.uuid_str = uuid_str
        self.cache_dir = Path(cache_dir)
        self.custom_skin_path = custom_skin_path
        self.model = model
        self.second_layer = second_layer
        self.view_mode = view_mode
        self.auth_mode = auth_mode
        self.username = username

    def run(self):
        skin_img = None
        model = self.model

        if self.custom_skin_path and Path(self.custom_skin_path).exists():
            img = QImage(self.custom_skin_path)
            if not img.isNull():
                skin_img = img

        clean_uuid = (self.uuid_str or "").replace("-", "")
        cape_img = None

        if not skin_img:
            if self.auth_mode != "offline":
                if not clean_uuid and self.username and self.username != "NeuraPlayer":
                    try:
                        u_resp = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{self.username}", timeout=5)
                        if u_resp.status_code == 200:
                            clean_uuid = u_resp.json().get("id", clean_uuid)
                    except Exception:
                        pass

                if clean_uuid and clean_uuid != "steve" and clean_uuid != "00000000000000000000000000000000":
                    cache_path = self.cache_dir / f"{clean_uuid}_skin.png"
                    if cache_path.exists():
                        img = QImage(str(cache_path))
                        if not img.isNull():
                            skin_img = img

                    # Check for locally cached official Mojang cape
                    cape_cache_path = self.cache_dir.parent / "capes" / f"{clean_uuid}_cape.png"
                    if cape_cache_path.exists():
                        c_img = QImage(str(cape_cache_path))
                        if not c_img.isNull():
                            cape_img = c_img

                    if not skin_img or not cape_img:
                        try:
                            url = f"https://sessionserver.mojang.com/session/minecraft/profile/{clean_uuid}"
                            resp = requests.get(url, timeout=10)
                            if resp.status_code == 200:
                                data = resp.json()
                                for prop in data.get("properties", []):
                                    if prop.get("name") == "textures":
                                        b64_val = prop.get("value", "")
                                        decoded_bytes = base64.b64decode(b64_val)
                                        decoded_json = json.loads(decoded_bytes.decode("utf-8"))
                                        textures = decoded_json.get("textures", {})
                                        
                                        # Official Mojang Skin
                                        skin_data = textures.get("SKIN", {})
                                        skin_url = skin_data.get("url", "")
                                        if skin_url:
                                            self.cache_dir.mkdir(parents=True, exist_ok=True)
                                            s_resp = requests.get(skin_url, timeout=10)
                                            if s_resp.status_code == 200:
                                                with open(cache_path, "wb") as f:
                                                    f.write(s_resp.content)
                                                img = QImage(str(cache_path))
                                                if not img.isNull():
                                                    skin_img = img
                                                    metadata = skin_data.get("metadata", {})
                                                    if metadata.get("model") == "slim":
                                                        model = "slim"
                                        
                                        # Official Mojang Cape
                                        cape_data = textures.get("CAPE", {})
                                        cape_url = cape_data.get("url", "")
                                        cape_cache_path.parent.mkdir(parents=True, exist_ok=True)
                                        if cape_url:
                                            c_resp = requests.get(cape_url, timeout=10)
                                            if c_resp.status_code == 200:
                                                with open(cape_cache_path, "wb") as f:
                                                    f.write(c_resp.content)
                                                c_img = QImage(str(cape_cache_path))
                                                if not c_img.isNull():
                                                    cape_img = c_img
                                        else:
                                            if cape_cache_path.exists():
                                                try:
                                                    cape_cache_path.unlink()
                                                except Exception:
                                                    pass
                        except Exception:
                            pass
        else:
            # If a local custom skin is being previewed, still show the official Mojang cape if linked
            if clean_uuid and clean_uuid != "steve" and clean_uuid != "00000000000000000000000000000000":
                cape_cache_path = self.cache_dir.parent / "capes" / f"{clean_uuid}_cape.png"
                if cape_cache_path.exists():
                    c_img = QImage(str(cape_cache_path))
                    if not c_img.isNull():
                        cape_img = c_img

        if not skin_img or skin_img.isNull():
            skin_img = create_default_steve_texture()

        rendered = render_skin_model(
            skin_img,
            model=model,
            second_layer=self.second_layer,
            view=self.view_mode,
            cape_img=cape_img
        )
        self.loaded.emit(rendered)
