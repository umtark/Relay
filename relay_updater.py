#!/usr/bin/env python3
"""
Relay Auto-Updater
==================
Relay proxy başlarken GitHub'dan güncelleme kontrolü yapar.
Yeni versiyon varsa dosyaları indirir ve günceller.

Kullanım:
    from relay_updater import check_and_update
    check_and_update()  # Proxy başlarken çağır
"""

import os
import sys
import json
import shutil
import tempfile
import urllib.request
import urllib.error

# ══════════════════════════════════════════════════════════
# AYARLAR
# ══════════════════════════════════════════════════════════

GITHUB_OWNER = "umtark"
GITHUB_REPO = "Relay"
GITHUB_BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}"

# Lokal version dosyası (script'in yanında veya workspace'de)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Extension içinde gömülüyse
if os.path.basename(_SCRIPT_DIR) == "relay" and ".vscode" in _SCRIPT_DIR:
    WORKSPACE_DIR = os.getcwd()
    EXT_RELAY_DIR = _SCRIPT_DIR
else:
    WORKSPACE_DIR = _SCRIPT_DIR
    EXT_RELAY_DIR = None

LOCAL_VERSION_FILE = os.path.join(WORKSPACE_DIR, "version.json")
UPDATE_TIMEOUT = 10  # saniye


def _fetch_json(url):
    """URL'den JSON çek."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Relay-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8-sig"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def _fetch_file(url):
    """URL'den dosya içeriğini çek (bytes)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Relay-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def _get_local_version():
    """Lokal versiyon bilgisini oku."""
    if os.path.isfile(LOCAL_VERSION_FILE):
        try:
            with open(LOCAL_VERSION_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": "0.0.0"}


def _write_local_version(data):
    """Lokal versiyon bilgisini yaz."""
    with open(LOCAL_VERSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _version_tuple(v):
    """'1.0.0' → (1, 0, 0)"""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _update_file(rel_path, content_bytes):
    """Dosyayı güncelle — workspace ve extension/relay kopyası."""
    updated = []

    # 1. Workspace kopyası
    ws_path = os.path.join(WORKSPACE_DIR, rel_path)
    ws_dir = os.path.dirname(ws_path)
    if not os.path.isdir(ws_dir):
        os.makedirs(ws_dir, exist_ok=True)
    with open(ws_path, "wb") as f:
        f.write(content_bytes)
    updated.append(ws_path)

    # 2. Extension/relay kopyası (eğer Relay_proxy.py ise)
    if EXT_RELAY_DIR and rel_path == "Relay_proxy.py":
        ext_path = os.path.join(EXT_RELAY_DIR, "Relay_proxy.py")
        with open(ext_path, "wb") as f:
            f.write(content_bytes)
        updated.append(ext_path)

    # 3. Extension/relay içindeki updater (kendini güncelle)
    if EXT_RELAY_DIR and rel_path == "relay_updater.py":
        ext_path = os.path.join(EXT_RELAY_DIR, "relay_updater.py")
        with open(ext_path, "wb") as f:
            f.write(content_bytes)
        updated.append(ext_path)

    return updated


def check_and_update(silent=False):
    """
    GitHub'dan güncelleme kontrol et ve uygula.
    
    Returns:
        dict: {"updated": bool, "old_version": str, "new_version": str, "files": list}
    """
    result = {"updated": False, "old_version": "?", "new_version": "?", "files": []}

    # Lokal versiyon
    local_data = _get_local_version()
    local_ver = local_data.get("version", "0.0.0")
    result["old_version"] = local_ver

    if not silent:
        print(f"  🔍 Güncelleme kontrolü... (lokal: v{local_ver})")

    # Remote versiyon
    remote_data = _fetch_json(f"{RAW_BASE}/version.json")
    if not remote_data:
        if not silent:
            print(f"  ⚠️  GitHub'a ulaşılamadı (çevrimdışı?)")
        return result

    remote_ver = remote_data.get("version", "0.0.0")
    result["new_version"] = remote_ver

    # Karşılaştır
    if _version_tuple(remote_ver) <= _version_tuple(local_ver):
        if not silent:
            print(f"  ✅ Güncel (v{local_ver})")
        return result

    # Güncelleme var!
    changelog = remote_data.get("changelog", "")
    files = remote_data.get("files", [])

    if not silent:
        print(f"  🆕 Yeni sürüm: v{remote_ver} (mevcut: v{local_ver})")
        if changelog:
            print(f"      Değişiklik: {changelog}")
        print(f"  📥 {len(files)} dosya güncelleniyor...")

    # Dosyaları indir ve güncelle
    updated_files = []
    for rel_path in files:
        url = f"{RAW_BASE}/{rel_path}"
        content = _fetch_file(url)
        if content:
            paths = _update_file(rel_path, content)
            updated_files.extend(paths)
            if not silent:
                print(f"  ✅ {rel_path}")
        else:
            if not silent:
                print(f"  ⚠️  İndirilemedi: {rel_path}")

    # Versiyon dosyasını güncelle
    _write_local_version(remote_data)

    result["updated"] = True
    result["files"] = updated_files
    result["changelog"] = changelog

    if not silent:
        print(f"  🎉 v{local_ver} → v{remote_ver} güncellendi!")
        if "Relay_proxy.py" in files:
            print(f"  ⚠️  Proxy güncellendi — yeniden başlatılması gerekiyor")

    return result


def notify_owner(action, machine_info=None):
    """
    Sahibine (Ümit Bey) bildirim gönder — GitHub Issue olarak.
    Kim indirdi, kim güncelledi bilgisi.
    """
    import platform
    if machine_info is None:
        machine_info = {
            "hostname": platform.node(),
            "os": platform.platform(),
            "user": os.environ.get("USERNAME", os.environ.get("USER", "bilinmiyor")),
        }

    title = f"[Relay] {action} — {machine_info['hostname']}"
    body = (
        f"**İşlem:** {action}\n"
        f"**Bilgisayar:** {machine_info['hostname']}\n"
        f"**Kullanıcı:** {machine_info['user']}\n"
        f"**İşletim Sistemi:** {machine_info['os']}\n"
        f"**Tarih:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )

    try:
        # GitHub API ile issue oluştur
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
        data = json.dumps({"title": title, "body": body, "labels": ["notification"]}).encode("utf-8")

        # Token'ı gh CLI'den al
        import subprocess
        token = subprocess.check_output(["gh", "auth", "token"], stderr=subprocess.DEVNULL).decode().strip()

        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "Relay-Updater/1.0"
        }, method="POST")

        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT) as resp:
            return resp.status == 201
    except Exception:
        return False


if __name__ == "__main__":
    print("═" * 50)
    print("  Relay Auto-Updater")
    print("═" * 50)
    result = check_and_update()
    if result["updated"]:
        print(f"\n  Güncelleme tamamlandı: {len(result['files'])} dosya")
    else:
        print(f"\n  Değişiklik yok")
