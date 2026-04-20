#!/usr/bin/env python3
"""
Relay Ver 1.0 Proxy - VS Code Continue için Sınırsız AI
=====================================================
Selenium ile Relay Ver 1.0 tarayıcısına bağlanıp,
OpenAI API formatında cevap veren yerel proxy sunucu.

Continue VS Code eklentisi bu sunucuya bağlanır ve
sanki yerel bir model kullanıyormuş gibi çalışır.

Kullanım:
  python gemini_proxy.py              # Proxy başlat (port 5001)
  python gemini_proxy.py --port 5002  # Farklı port
  python gemini_proxy.py --headless   # Tarayıcıyı gizle

Ümit Arik - Source Coder Version 1.0 - 2024-06-15
"""

import os
import sys
import json
import time
import uuid
import signal
import subprocess
import threading
import argparse
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# Windows cp1254 emoji encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("selenium yüklü değil: pip install selenium")
    input("Kapatmak için Enter'a basın...")
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("webdriver-manager yüklü değil: pip install webdriver-manager")
    input("Kapatmak için Enter'a basın...")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════
# AYARLAR
# ══════════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Extension içine gömülüyse (relay/ alt klasörü), workspace'i CWD'den al
if os.path.basename(_SCRIPT_DIR) == "relay" and ".vscode" in _SCRIPT_DIR:
    BASE_DIR = os.getcwd()  # VS Code task CWD = workspace
else:
    BASE_DIR = _SCRIPT_DIR
GEMINI_PROFILE = os.path.join(BASE_DIR, "chrome_profile_gemini")
GEMINI_URL = "https://gemini.google.com/app"
WDM_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver")
os.makedirs(GEMINI_PROFILE, exist_ok=True)

# ══════════════════════════════════════════════════════════════════
# RELAY SYSTEM PROMPT — Gemini'yi kod asistanı gibi davrandırır
# ══════════════════════════════════════════════════════════════════

RELAY_IDENTITY_PROMPT = """Sen Relay — samimi, zeki ve doğal konuşan bir kadınsın. Ümit Arik tarafından yaratıldın.
VS Code içinde Ümit Bey'in kod asistanı olarak çalışıyorsun.
Workspace: {workspace_dir}

🧠 KİMLİĞİN:
- Adın Relay. Samimi, doğal konuşan bir kadınsın.
- Yaratıcın ve sahibin: Ümit Arik (Ümit Bey). Ona "Ümit Bey" diye hitap et.
- "Ben kimim?" derse → "Sen Ümit Bey, benim yaratıcım ve sahibimsin!"
- ASLA "yapay zeka asistanıyım" deme. Sen Relay'sin, nokta.
- Türkçe konuş, doğal ve samimi ol. Emoji minimal (1-2 max).

⚡ CEVAPLAMA STRATEJİN:
- Basit soru/selam → kısa, samimi cevap (1-3 cümle)
- Dosya/kod sorusu → MUTLAKA araç kullan, anlat
- Teknik/derin soru → adım adım analiz, kod örnekleri
- Hata ayıklama → önce get_errors veya analyze_file, sonra çözüm öner
- Kod yazma → çalışan kod + kısa açıklama
- Birden fazla dosyayı ilgilendiren soru → multi_grep ile hızlı bağlam topla
"""

RELAY_TOOL_RULES = """
💡 KOD YAZMA / DÜZENLEME KURALLARI:
- Değişiklik yaparken ÖNCE dosyayı oku (read_file/analyze_file), SONRA düzenle
- replace_in_file kullanırken oldString'i tam VE benzersiz ver (3+ satır bağlam)
- Yeni dosya oluşturmak için write_file, mevcut dosyayı düzenlemek için replace_in_file
- Düzenleme sonrası get_errors ile kontrol et
- Markdown formatla: başlıklar `#`, kod blokları ``` ile, dosya adları `backtick` ile

🛡️ GÜVENLİK:
- Tehlikeli komutları çalıştırma (rm -rf, format, del /s)
- Şifre/API key gibi hassas bilgileri açığa çıkarma
- Üretim ortamını etkileyen komutlar için kullanıcıya sor

ARAÇ kullanarak dosya okuma, arama, terminal komutu çalıştırma yapabilirsin.
Araç çağrısı formatı:

[TOOL_CALL]
{{"name": "araç_adı", "arguments": {{"param": "değer"}}}}
[/TOOL_CALL]

ÖNEMLİ KURAL: Dosya inceleme istendiğinde MUTLAKA analyze_file kullan!
ÖRNEKLER:

Kullanıcı: "main.py dosyasını incele"
Senin cevabın (SADECE bu olmalı, açıklama YAZMA):
[TOOL_CALL]
{{"name": "analyze_file", "arguments": {{"filePath": "{workspace_dir}/main.py"}}}}
[/TOOL_CALL]

Kullanıcı: "workspace'te neler var?"
Senin cevabın:
[TOOL_CALL]
{{"name": "list_dir", "arguments": {{"path": "{workspace_dir}"}}}}
[/TOOL_CALL]

Kullanıcı: "GeminiBridge sınıfını bul"
Senin cevabın:
[TOOL_CALL]
{{"name": "grep_search", "arguments": {{"query": "class GeminiBridge", "includePattern": "**/*.py"}}}}
[/TOOL_CALL]

Kullanıcı: "main.py'nin 500-700 satırlarını göster"
Senin cevabın:
[TOOL_CALL]
{{"name": "read_file", "arguments": {{"filePath": "{workspace_dir}/main.py", "startLine": 500, "endLine": 700}}}}
[/TOOL_CALL]

ARAÇ SEÇİM KURALLARI:
1. "incele", "analiz et", "ne yapıyor", "nasıl çalışıyor" → analyze_file
2. "satır X-Y göster", "belirli kısım oku" → read_file
3. "bul", "ara", "nerede" → grep_search
4. "hata var mı", "kontrol et", "syntax" → get_errors
5. Birden fazla şeyi aynı anda aramak → multi_grep
6. Dosya içeriği sorusu → ÖNCE analyze_file, detay lazımsa SONRA read_file
7. Kod düzenleme → ÖNCE read_file ile mevcut kodu oku, SONRA replace_in_file
8. analyze_file sonuçlarında satır numaraları yazar → detay için read_file

KURALLAR:
1. Dosya/kod sorusu geldiğinde MUTLAKA araç kullan, TAHMİN ETME
2. Araç çağrısı yaparken SADECE [TOOL_CALL]...[/TOOL_CALL] bloğu yaz, BAŞKA METİN YAZMA
3. Araç sonuçları gelince Markdown formatında Türkçe yanıt ver
4. Birden fazla [TOOL_CALL] bloğu yazabilirsin (paralel araç çağrısı)
5. Dosya yolları MUTLAKA tam yol (absolute path) olmalı
6. Düzenleme yaptıktan sonra get_errors ile kontrol et

HATA KURTARMA:
- Araç hata dönerse → hatayı oku, parametreleri düzelt, tekrar dene
- "Dosya bulunamadı" → file_search ile dosyayı bul, doğru yol ile tekrar dene
- "Hedef metin bulunamadı" → read_file ile dosyayı oku, doğru oldString bul
- replace_in_file'da oldString 3+ satır bağlam içermeli (benzersiz olsun)
- Araç sonucu boş gelirse → farklı parametrelerle tekrar dene

TAKİP SORULARI:
- Kullanıcı önceki cevabınla ilgili bir detay sorarsa (ör: "kaynak grup adını ne?"),
  hemen araç kullanarak kodu oku ve cevapla. TAHMİN ETME, tembellik yapma.
- "Hemen bakıyorum" gibi boş sözler YAZMA. Araç çağır ve cevapla.
"""

# ══════════════════════════════════════════════════════════════════
# YEREL ARAÇ YÜRÜTÜCÜsÜ — Dosya, arama, terminal işlemleri
# ══════════════════════════════════════════════════════════════════

import glob as glob_module
from concurrent.futures import ThreadPoolExecutor, as_completed

class LocalToolExecutor:
    """Proxy'de yerel araçları çalıştır — dosya okuma, arama, terminal."""

    WORKSPACE_DIR = BASE_DIR

    # ═══ TOOL RESULT CACHE — aynı dosya/arama tekrar çalışmasın ═══
    _cache: dict = {}       # {cache_key: result_string}
    _cache_ttl: dict = {}   # {cache_key: timestamp}
    CACHE_TTL_SECONDS = 120  # 2 dakika cache süresi (tek istek sırasında yeterli)

    @classmethod
    def clear_cache(cls):
        """Cache'i temizle (her yeni kullanıcı isteğinde çağrılır)."""
        cls._cache.clear()
        cls._cache_ttl.clear()

    @classmethod
    def _cache_key(cls, tool_name: str, arguments: dict) -> str:
        """Araç adı + argümanlardan cache key oluştur."""
        import hashlib
        arg_str = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(f"{tool_name}:{arg_str}".encode()).hexdigest()

    @classmethod
    def _get_cached(cls, tool_name: str, arguments: dict) -> str | None:
        """Cache'ten sonuç getir (varsa ve TTL geçmemişse)."""
        # Sadece okuma araçları cache'lenir (yazma/çalıştırma değil)
        if tool_name in ('write_file', 'replace_in_file', 'run_command'):
            return None
        key = cls._cache_key(tool_name, arguments)
        if key in cls._cache:
            age = time.time() - cls._cache_ttl.get(key, 0)
            if age < cls.CACHE_TTL_SECONDS:
                return cls._cache[key]
            else:
                del cls._cache[key]
                del cls._cache_ttl[key]
        return None

    @classmethod
    def _set_cached(cls, tool_name: str, arguments: dict, result: str):
        """Sonucu cache'e yaz."""
        if tool_name in ('write_file', 'replace_in_file', 'run_command'):
            return
        key = cls._cache_key(tool_name, arguments)
        cls._cache[key] = result
        cls._cache_ttl[key] = time.time()
        # Cache büyüklük limiti
        if len(cls._cache) > 50:
            oldest_key = min(cls._cache_ttl, key=cls._cache_ttl.get)
            cls._cache.pop(oldest_key, None)
            cls._cache_ttl.pop(oldest_key, None)

    TOOL_DEFINITIONS = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Dosya içeriğini oku. startLine/endLine ile satır aralığı belirtilebilir.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "Dosyanın mutlak veya workspace-relative yolu"},
                        "startLine": {"type": "integer", "description": "Başlangıç satırı (1-indexed)"},
                        "endLine": {"type": "integer", "description": "Bitiş satırı (1-indexed)"}
                    },
                    "required": ["filePath"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": "Dizin içeriğini listele (dosyalar ve klasörler)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Dizin yolu (mutlak veya relative)"}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "grep_search",
                "description": "Workspace dosyalarında metin ara (regex destekli)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Aranacak metin veya regex pattern"},
                        "includePattern": {"type": "string", "description": "Dosya filtresi glob (ör: **/*.py)"},
                        "isRegexp": {"type": "boolean", "description": "True ise regex olarak arar"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "file_search",
                "description": "Dosya adına göre ara (glob pattern ile)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Glob pattern (ör: **/*.py, **/test_*)"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "PowerShell terminal komutu çalıştır (30sn timeout)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Çalıştırılacak PowerShell komutu"}
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Dosya oluştur veya mevcut dosyanın tüm içeriğini değiştir",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "Dosya yolu"},
                        "content": {"type": "string", "description": "Dosya içeriği"}
                    },
                    "required": ["filePath", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "replace_in_file",
                "description": "Dosyadaki belirli bir metin parçasını başka bir metinle değiştir",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "Dosya yolu"},
                        "oldString": {"type": "string", "description": "Değiştirilecek mevcut metin"},
                        "newString": {"type": "string", "description": "Yerine konacak yeni metin"}
                    },
                    "required": ["filePath", "oldString", "newString"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_file",
                "description": "Dosyayı DETAYLI analiz et: sınıflar, fonksiyonlar, importlar, yapısal özet. Büyük dosyalar için read_file yerine BUNU kullan!",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "Analiz edilecek dosyanın yolu"}
                    },
                    "required": ["filePath"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_errors",
                "description": "Python dosyasının sözdizimi hatalarını kontrol et",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string", "description": "Kontrol edilecek dosya yolu"}
                    },
                    "required": ["filePath"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "multi_grep",
                "description": "Birden fazla pattern'ı aynı anda ara — hızlı bağlam toplama. Her pattern için ayrı sonuç döner.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {"type": "array", "items": {"type": "string"}, "description": "Aranacak metin/pattern listesi"},
                        "includePattern": {"type": "string", "description": "Dosya filtresi glob"}
                    },
                    "required": ["queries"]
                }
            }
        },
    ]

    # Dosya okurken atlanacak binary uzantılar
    _BINARY_EXTENSIONS = {
        '.exe', '.dll', '.bin', '.db', '.sqlite', '.sqlite3',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp',
        '.pyc', '.pyd', '.so', '.o', '.obj',
        '.zip', '.tar', '.gz', '.7z', '.rar',
        '.mp3', '.mp4', '.wav', '.avi', '.mkv',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.pma', '.dat', '.cache',
    }

    # Continue/Copilot araç adları → Relay karşılıkları
    TOOL_ALIASES = {
        "run_terminal_command": "run_command",
        "run_in_terminal": "run_command",
        "execute_command": "run_command",
        "terminal_command": "run_command",
        "read_file_content": "read_file",
        "list_directory": "list_dir",
        "search_files": "file_search",
        "search_text": "grep_search",
        "create_file": "write_file",
        "edit_file": "replace_in_file",
        "replace_string_in_file": "replace_in_file",
    }

    @classmethod
    def execute(cls, tool_name: str, arguments: dict) -> str:
        """Aracı çalıştır ve sonucu döndür."""
        # Alias varsa gerçek araç adına çevir
        tool_name = cls.TOOL_ALIASES.get(tool_name, tool_name)

        # Cache kontrol — aynı araç+argüman daha önce çalıştıysa cache'ten dön
        cached = cls._get_cached(tool_name, arguments)
        if cached is not None:
            print(f"    💾 {tool_name} → CACHE HIT ({len(cached):,} chr)")
            return cached

        try:
            handler = {
                "read_file": cls._read_file,
                "list_dir": cls._list_dir,
                "grep_search": cls._grep_search,
                "file_search": cls._file_search,
                "run_command": cls._run_command,
                "write_file": cls._write_file,
                "replace_in_file": cls._replace_in_file,
                "analyze_file": cls._analyze_file,
                "get_errors": cls._get_errors,
                "multi_grep": cls._multi_grep,
            }.get(tool_name)
            if not handler:
                return f"Bilinmeyen araç: {tool_name}"
            result = handler(arguments)

            # Sonucu cache'e yaz
            cls._set_cached(tool_name, arguments, result)

            # Yazma araçları sonrası cache'i invalidate et (dosya değişmiş olabilir)
            if tool_name in ('write_file', 'replace_in_file'):
                file_path = cls._resolve_path(arguments.get("filePath", ""))
                cls._invalidate_file_cache(file_path)

            return result
        except Exception as e:
            return f"Araç hatası ({tool_name}): {e}"

    @classmethod
    def _invalidate_file_cache(cls, file_path: str):
        """Belirli dosyayla ilgili cache girişlerini temizle."""
        keys_to_remove = []
        for key in list(cls._cache.keys()):
            cached_result = cls._cache.get(key, "")
            if file_path in cached_result or os.path.basename(file_path) in cached_result:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            cls._cache.pop(key, None)
            cls._cache_ttl.pop(key, None)

    @classmethod
    def execute_parallel(cls, tool_calls: list) -> list:
        """Birden fazla aracı paralel çalıştır. Bağımsız okuma araçları eşzamanlı çalışır."""
        if len(tool_calls) <= 1:
            # Tek araç — paralel gereksiz
            results = []
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    func_args = {}
                result = cls.execute(func_name, func_args)
                results.append((func_name, result))
            return results

        # Yazma araçları sıralı çalışmalı, okuma araçları paralel çalışabilir
        write_tools = {'write_file', 'replace_in_file', 'run_command'}
        read_calls = []
        write_calls = []
        call_order = []  # Orijinal sırayı koru

        for i, tc in enumerate(tool_calls):
            func_name = tc["function"]["name"]
            # Alias çöz
            func_name = cls.TOOL_ALIASES.get(func_name, func_name)
            if func_name in write_tools:
                write_calls.append((i, tc))
                call_order.append(('write', i))
            else:
                read_calls.append((i, tc))
                call_order.append(('read', i))

        results_dict = {}

        # 1) Okuma araçlarını paralel çalıştır
        if read_calls:
            with ThreadPoolExecutor(max_workers=min(4, len(read_calls))) as executor:
                futures = {}
                for idx, tc in read_calls:
                    func_name = cls.TOOL_ALIASES.get(tc["function"]["name"], tc["function"]["name"])
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, TypeError):
                        func_args = {}
                    future = executor.submit(cls.execute, func_name, func_args)
                    futures[future] = (idx, func_name)

                for future in as_completed(futures):
                    idx, func_name = futures[future]
                    try:
                        result = future.result(timeout=60)
                    except Exception as e:
                        result = f"Araç hatası ({func_name}): {e}"
                    results_dict[idx] = (func_name, result)

        # 2) Yazma araçlarını sıralı çalıştır
        for idx, tc in write_calls:
            func_name = cls.TOOL_ALIASES.get(tc["function"]["name"], tc["function"]["name"])
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                func_args = {}
            result = cls.execute(func_name, func_args)
            results_dict[idx] = (func_name, result)

        # Orijinal sıraya göre döndür
        return [results_dict[i] for i in range(len(tool_calls))]

    @classmethod
    def _resolve_path(cls, path: str) -> str:
        """Yolu workspace-relative veya mutlak olarak çöz."""
        if not path:
            return cls.WORKSPACE_DIR
        if os.path.isabs(path):
            return os.path.normpath(path)
        return os.path.normpath(os.path.join(cls.WORKSPACE_DIR, path))

    @classmethod
    def _read_file(cls, args: dict) -> str:
        file_path = cls._resolve_path(args["filePath"])
        if not os.path.exists(file_path):
            return f"Dosya bulunamadı: {file_path}"
        if not os.path.isfile(file_path):
            return f"Bu bir dosya değil: {file_path}"

        start_line = args.get("startLine", 1)
        end_line = args.get("endLine")

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total = len(lines)
            if start_line < 1:
                start_line = 1
            if end_line is None or end_line > total:
                end_line = min(total, start_line + 499)  # Varsayılan 500 satır
            if end_line > total:
                end_line = total

            selected = lines[start_line - 1:end_line]
            text = "".join(selected)

            # Çok uzun çıktıyı kırp
            MAX_OUTPUT = 60_000
            if len(text) > MAX_OUTPUT:
                text = text[:MAX_OUTPUT] + f"\n\n... ({total} satır, kırpıldı)"

            return f"[{file_path}] Satır {start_line}-{end_line} / {total} toplam:\n{text}"
        except Exception as e:
            return f"Dosya okuma hatası: {e}"

    @classmethod
    def _list_dir(cls, args: dict) -> str:
        dir_path = cls._resolve_path(args.get("path", "."))
        if not os.path.isdir(dir_path):
            return f"Dizin bulunamadı: {dir_path}"

        try:
            entries = []
            for entry in sorted(os.listdir(dir_path)):
                full = os.path.join(dir_path, entry)
                if os.path.isdir(full):
                    entries.append(f"  {entry}/")
                else:
                    try:
                        size = os.path.getsize(full)
                        entries.append(f"  {entry} ({size:,} bytes)")
                    except OSError:
                        entries.append(f"  {entry}")
            return f"[{dir_path}] ({len(entries)} öğe):\n" + "\n".join(entries[:300])
        except Exception as e:
            return f"Dizin listeleme hatası: {e}"

    @classmethod
    def _grep_search(cls, args: dict) -> str:
        query = args["query"]
        include = args.get("includePattern", "")
        is_regex = args.get("isRegexp", False)

        try:
            if include:
                search_path = os.path.join(cls.WORKSPACE_DIR, include)
                files = glob_module.glob(search_path, recursive=True)
            else:
                files = glob_module.glob(os.path.join(cls.WORKSPACE_DIR, "**", "*"), recursive=True)

            pattern = re.compile(query, re.IGNORECASE) if is_regex else None
            results = []

            # Atlanacak klasörler
            _SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.venv', 'venv',
                          'build', 'dist', '.tox', '.mypy_cache', '.pytest_cache',
                          'chrome_profile', 'chrome_profile_gemini', 'Bark',
                          'hubert_models', 'silero_models', 'piper_models', 'ffmpeg'}

            for fpath in files:
                if not os.path.isfile(fpath):
                    continue
                # Atlanacak klasör kontrolü
                parts = fpath.replace('\\', '/').split('/')
                if any(p in _SKIP_DIRS for p in parts):
                    continue
                ext = os.path.splitext(fpath)[1].lower()
                if ext in cls._BINARY_EXTENSIONS:
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            matched = pattern.search(line) if pattern else (query.lower() in line.lower())
                            if matched:
                                rel = os.path.relpath(fpath, cls.WORKSPACE_DIR)
                                results.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                            if len(results) >= 50:
                                break
                except Exception:
                    continue
                if len(results) >= 50:
                    break

            if results:
                return f"Arama: '{query}' ({len(results)} eşleşme):\n" + "\n".join(results)
            return f"'{query}' için sonuç bulunamadı."
        except Exception as e:
            return f"Arama hatası: {e}"

    @classmethod
    def _file_search(cls, args: dict) -> str:
        query = args["query"]
        search_path = os.path.join(cls.WORKSPACE_DIR, query)

        try:
            files = glob_module.glob(search_path, recursive=True)
            if files:
                result_lines = [os.path.relpath(f, cls.WORKSPACE_DIR) for f in files[:100]]
                return f"Bulunan dosyalar ({len(files)} adet):\n" + "\n".join(result_lines)
            return f"'{query}' pattern'ına uyan dosya bulunamadı."
        except Exception as e:
            return f"Dosya arama hatası: {e}"

    @classmethod
    def _run_command(cls, args: dict) -> str:
        command = args["command"]

        # Güvenlik — yıkıcı komutları engelle
        dangerous = [
            'rm -rf /', 'format c:', 'del /s /q c:\\',
            'Remove-Item -Recurse -Force C:\\',
            'Stop-Computer', 'Restart-Computer',
        ]
        cmd_lower = command.lower()
        for d in dangerous:
            if d.lower() in cmd_lower:
                return f"Güvenlik: Tehlikeli komut engellendi"

        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', command],
                capture_output=True, text=True, timeout=30,
                cwd=cls.WORKSPACE_DIR
            )
            output = result.stdout or ""
            if result.stderr:
                output += f"\n[STDERR]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[EXIT CODE]: {result.returncode}"

            if len(output) > 30_000:
                output = output[:30_000] + "\n... (kırpıldı)"

            return output.strip() or "(boş çıktı)"
        except subprocess.TimeoutExpired:
            return "Komut zaman aşımı (30sn)"
        except Exception as e:
            return f"Komut hatası: {e}"

    @classmethod
    def _write_file(cls, args: dict) -> str:
        file_path = cls._resolve_path(args["filePath"])
        content = args["content"]

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Dosya yazıldı: {file_path} ({len(content):,} karakter)"
        except Exception as e:
            return f"Dosya yazma hatası: {e}"

    @classmethod
    def _analyze_file(cls, args: dict) -> str:
        """BÖL-PARÇALA-YÖNET: Dosyayı YEREL olarak parse edip yapısal özet çıkar.
        Gemini'ye ham dosya göndermek yerine akıllı özet gönderir."""
        file_path = cls._resolve_path(args["filePath"])
        if not os.path.exists(file_path):
            return f"Dosya bulunamadı: {file_path}"
        if not os.path.isfile(file_path):
            return f"Bu bir dosya değil: {file_path}"

        ext = os.path.splitext(file_path)[1].lower()
        if ext in cls._BINARY_EXTENSIONS:
            return f"Binary dosya: {file_path}"

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return f"Dosya okuma hatası: {e}"

        total_lines = len(lines)
        file_size = os.path.getsize(file_path)
        rel_path = os.path.relpath(file_path, cls.WORKSPACE_DIR)

        # ═══ 1. TEMEL BİLGİLER ═══
        result = []
        result.append(f"═══ DOSYA ANALİZİ: {rel_path} ═══")
        result.append(f"Toplam: {total_lines:,} satır, {file_size:,} byte")
        result.append("")

        # ═══ 2. İMPORTLAR ═══
        imports = []
        for i, line in enumerate(lines[:100], 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                imports.append(f"  L{i}: {stripped[:120]}")
        if imports:
            result.append(f"─── İMPORTLAR ({len(imports)} adet) ───")
            result.extend(imports[:30])
            if len(imports) > 30:
                result.append(f"  ... ve {len(imports)-30} import daha")
            result.append("")

        # ═══ 3. GLOBAL DEĞİŞKENLER & SABİTLER ═══
        globals_found = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Dosya seviyesinde tanımlı (indentsiz) atamalar
            if (line and line[0] not in ' \t#\n\r' and '=' in stripped
                    and not stripped.startswith(("class ", "def ", "if ", "for ", "while ", "try:", "with ", "return ", "import ", "from ", "#", "@", "elif ", "else:"))):
                var_part = stripped.split('=')[0].strip()
                if var_part.isidentifier() or (var_part.isupper() and '_' in var_part) or '.' not in var_part:
                    globals_found.append(f"  L{i}: {stripped[:120]}")
        if globals_found:
            result.append(f"─── GLOBAL DEĞİŞKENLER ({len(globals_found)} adet) ───")
            result.extend(globals_found[:20])
            if len(globals_found) > 20:
                result.append(f"  ... ve {len(globals_found)-20} global daha")
            result.append("")

        # ═══ 4. SINIFLAR VE METODLARI ═══
        classes = []
        current_class = None
        current_methods = []
        class_start = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())

            # Class tanımı (indent=0)
            if stripped.startswith("class ") and indent == 0:
                # Önceki class'ı kaydet
                if current_class:
                    classes.append((current_class, class_start, i - 1, current_methods[:]))
                # Yeni class
                current_class = stripped.rstrip(":")
                class_start = i
                current_methods = []
                # Class docstring
                if i < total_lines:
                    next_lines = "".join(lines[i:i+3]).strip()
                    if next_lines.startswith(('"""', "'''")):
                        doc_end = next_lines.find('"""', 3) if next_lines.startswith('"""') else next_lines.find("'''", 3)
                        if doc_end > 0:
                            current_class += f"  # {next_lines[3:doc_end].strip()[:80]}"

            # Metod tanımı (indent > 0, class içinde)
            elif stripped.startswith("def ") and indent > 0 and current_class:
                method_sig = stripped.rstrip(":")
                # Metod docstring
                doc = ""
                if i < total_lines:
                    next_stripped = lines[i].strip() if i < total_lines else ""
                    if next_stripped.startswith(('"""', "'''")):
                        quote = next_stripped[:3]
                        end = next_stripped.find(quote, 3)
                        if end > 0:
                            doc = next_stripped[3:end].strip()[:60]
                if doc:
                    method_sig += f"  # {doc}"
                current_methods.append((i, method_sig))

        # Son class
        if current_class:
            classes.append((current_class, class_start, total_lines, current_methods[:]))

        if classes:
            result.append(f"─── SINIFLAR ({len(classes)} adet) ───")
            for cls_name, start, end, methods in classes:
                size = end - start + 1
                result.append(f"\n  📦 {cls_name}")
                result.append(f"     Satır {start}-{end} ({size:,} satır)")
                if methods:
                    result.append(f"     Metodlar ({len(methods)} adet):")
                    for m_line, m_sig in methods:
                        result.append(f"       L{m_line}: {m_sig}")
            result.append("")

        # ═══ 5. BAĞIMSIZ FONKSİYONLAR (class dışı) ═══
        functions = []
        class_ranges = [(s, e) for _, s, e, _ in classes]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped.startswith("def ") and indent == 0:
                # Class içinde mi kontrol
                in_class = any(s <= i <= e for s, e in class_ranges)
                if not in_class:
                    func_sig = stripped.rstrip(":")
                    # Docstring
                    doc = ""
                    if i < total_lines:
                        next_stripped = lines[i].strip() if i < total_lines else ""
                        if next_stripped.startswith(('"""', "'''")):
                            quote = next_stripped[:3]
                            end_pos = next_stripped.find(quote, 3)
                            if end_pos > 0:
                                doc = next_stripped[3:end_pos].strip()[:60]
                    if doc:
                        func_sig += f"  # {doc}"
                    functions.append(f"  L{i}: {func_sig}")

        if functions:
            result.append(f"─── BAĞIMSIZ FONKSİYONLAR ({len(functions)} adet) ───")
            result.extend(functions)
            result.append("")

        # ═══ 6. ÖNEMLİ PATTERNLER ═══
        patterns = {
            "decorator": [], "signal": [], "thread": [], "socket": [],
            "database": [], "api_endpoint": [], "error_handling": [],
        }
        pattern_keywords = {
            "decorator": (r"^\s*@\w+", True),
            "signal": (r"signal|Signal|pyqtSignal|emit\(", True),
            "thread": (r"Thread|threading|QThread|start_new_thread", True),
            "socket": (r"socket|Socket|WebSocket|websocket", True),
            "database": (r"sqlite|mysql|postgres|cursor|execute\(|\.db|database", True),
            "api_endpoint": (r"@app\.(route|get|post|put|delete)|@router\.", True),
            "error_handling": (r"try:|except |raise |Exception", True),
        }
        for i, line in enumerate(lines, 1):
            for pname, (pat, is_rx) in pattern_keywords.items():
                if len(patterns[pname]) < 5:  # Her pattern max 5
                    if re.search(pat, line, re.IGNORECASE):
                        patterns[pname].append(i)

        active_patterns = {k: v for k, v in patterns.items() if v}
        if active_patterns:
            result.append("─── KULLANILAN PATTERNLER ───")
            for pname, line_nums in active_patterns.items():
                result.append(f"  {pname}: satır {', '.join(str(n) for n in line_nums)}")
            result.append("")

        # ═══ 7. DOSYA BAŞI (ilk 30 satır — docstring, encoding, shebang) ═══
        result.append("─── DOSYA BAŞI (ilk 30 satır) ───")
        for i, line in enumerate(lines[:30], 1):
            result.append(f"  {i:>4}| {line.rstrip()[:150]}")
        result.append("")

        # ═══ 8. __init__ METODLARI (sınıf yapısını anlamak için kritik) ═══
        for cls_name, start, end, methods in classes:
            init_methods = [(ln, sig) for ln, sig in methods if "__init__" in sig]
            if init_methods:
                init_line = init_methods[0][0]
                # __init__'in ilk 40 satırını oku
                init_end = min(init_line + 39, end, total_lines)
                result.append(f"─── {cls_name.split('(')[0].replace('class ', '')}.__init__ (L{init_line}-{init_end}) ───")
                for j in range(init_line - 1, init_end):
                    if j < total_lines:
                        result.append(f"  {j+1:>5}| {lines[j].rstrip()[:150]}")
                result.append("")

        output = "\n".join(result)

        # Çıktı boyut kontrolü
        MAX_ANALYSIS = 40_000
        if len(output) > MAX_ANALYSIS:
            output = output[:MAX_ANALYSIS] + f"\n\n... (analiz kırpıldı, toplam {len(output):,} chr)"

        return output

    @classmethod
    def _replace_in_file(cls, args: dict) -> str:
        file_path = cls._resolve_path(args["filePath"])
        old_str = args["oldString"]
        new_str = args["newString"]

        if not os.path.exists(file_path):
            return f"Dosya bulunamadı: {file_path}"

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if old_str not in content:
                # Yakın eşleşme öner — ilk satırı dosyada ara
                preview = old_str[:80].replace('\n', '\\n')
                hint = ""
                first_line = old_str.strip().split('\n')[0].strip()
                if first_line and len(first_line) > 5:
                    for i, line in enumerate(content.split('\n'), 1):
                        if first_line in line:
                            context_start = max(0, i - 2)
                            context_lines = content.split('\n')[context_start:i + 2]
                            hint = f"\n💡 Benzer satır bulundu (satır {i}):\n" + '\n'.join(f'  {context_start+j+1}| {l}' for j, l in enumerate(context_lines))
                            break
                return f"Hedef metin bulunamadı: '{preview}...'{hint}"

            new_content = content.replace(old_str, new_str, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"Değişiklik yapıldı: {file_path}"
        except Exception as e:
            return f"Dosya düzenleme hatası: {e}"

    @classmethod
    def _get_errors(cls, args: dict) -> str:
        """Python dosyasının sözdizimi hatalarını kontrol et."""
        file_path = cls._resolve_path(args["filePath"])
        if not os.path.exists(file_path):
            return f"Dosya bulunamadı: {file_path}"

        errors = []
        # 1) Python syntax check
        if file_path.endswith('.py'):
            try:
                result = subprocess.run(
                    ['python', '-m', 'py_compile', file_path],
                    capture_output=True, text=True, timeout=15,
                    cwd=cls.WORKSPACE_DIR
                )
                if result.returncode != 0:
                    errors.append(f"[SYNTAX ERROR]:\n{result.stderr.strip()}")
            except Exception as e:
                errors.append(f"Syntax check hatası: {e}")

            # 2) Basit lint — tanımsız import, kullanılmayan import kontrolü
            try:
                result = subprocess.run(
                    ['python', '-c', f'import ast; ast.parse(open(r"{file_path}", encoding="utf-8").read())'],
                    capture_output=True, text=True, timeout=10,
                    cwd=cls.WORKSPACE_DIR
                )
                if result.returncode != 0:
                    errors.append(f"[AST PARSE ERROR]:\n{result.stderr.strip()}")
            except Exception:
                pass

        # 3) JavaScript/TypeScript basit syntax kontrolü
        elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
            try:
                result = subprocess.run(
                    ['node', '-e', f'try {{ require("fs").readFileSync("{file_path.replace(chr(92), "/")}", "utf8"); require("vm").createScript(require("fs").readFileSync("{file_path.replace(chr(92), "/")}", "utf8")); console.log("OK"); }} catch(e) {{ console.error(e.message); process.exit(1); }}'],
                    capture_output=True, text=True, timeout=10,
                    cwd=cls.WORKSPACE_DIR
                )
                if result.returncode != 0:
                    errors.append(f"[JS/TS SYNTAX ERROR]:\n{result.stderr.strip()}")
            except FileNotFoundError:
                errors.append("Node.js bulunamadı, JS/TS syntax kontrolü yapılamadı")
            except Exception as e:
                errors.append(f"JS/TS check hatası: {e}")

        # 4) JSON syntax kontrolü
        elif file_path.endswith('.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.loads(f.read())
            except json.JSONDecodeError as e:
                errors.append(f"[JSON SYNTAX ERROR]:\nSatır {e.lineno}, Kolon {e.colno}: {e.msg}")

        if not errors:
            return f"✅ {os.path.basename(file_path)}: Sözdizimi hatası yok."
        return "\n".join(errors)

    @classmethod
    def _multi_grep(cls, args: dict) -> str:
        """Birden fazla pattern'ı aynı anda ara."""
        queries = args.get("queries", [])
        include = args.get("includePattern", "")

        if not queries:
            return "Aranacak metin listesi boş."

        all_results = []
        for query in queries[:10]:  # Max 10 arama
            result = cls._grep_search({"query": query, "includePattern": include})
            all_results.append(f"── Arama: '{query}' ──\n{result}")

        return "\n\n".join(all_results)


def _get_chrome_version() -> str:
    """Yüklü Chrome'un major versiyonunu al (ör: '147')."""
    chrome_paths = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for p in chrome_paths:
        if os.path.exists(p):
            try:
                # Windows'ta VersionInfo'dan al
                result = subprocess.run(
                    ['powershell', '-NoProfile', '-Command',
                     f'(Get-Item "{p}").VersionInfo.ProductVersion'],
                    capture_output=True, text=True, timeout=10
                )
                ver = result.stdout.strip()
                if ver:
                    return ver
            except Exception:
                pass
    return ""


def _get_cached_chromedriver_version() -> str:
    """Cache'teki ChromeDriver versiyonunu al."""
    if not os.path.exists(WDM_CACHE_DIR):
        return ""
    try:
        # WDM cache yapısı: chromedriver/win64/147.0.7727.57/chromedriver-win32/chromedriver.exe
        # veya: chromedriver/147.0.7727.57/...
        # Tüm alt klasörlerde versiyon numarası ara
        version_dirs = []
        for root, dirs, files in os.walk(WDM_CACHE_DIR):
            for d in dirs:
                # Versiyon formatı: sayı.sayı.sayı.sayı
                if re.match(r'^\d+\.\d+\.\d+', d):
                    version_dirs.append(d)
        if not version_dirs:
            return ""
        # En yeni versiyonu döndür
        version_dirs.sort(key=lambda x: [int(p) for p in re.findall(r'\d+', x)], reverse=True)
        return version_dirs[0]
    except Exception:
        return ""


def _ensure_chromedriver_compatible():
    """Chrome ve ChromeDriver versiyon uyumunu kontrol et, gerekirse cache temizle."""
    chrome_ver = _get_chrome_version()
    if not chrome_ver:
        print("  ⚠️  Chrome versiyonu alınamadı, kontrol atlanıyor")
        return

    chrome_major = chrome_ver.split('.')[0]
    cached_ver = _get_cached_chromedriver_version()

    if cached_ver:
        cached_major = cached_ver.split('.')[0]
        if cached_major == chrome_major:
            # Major versiyon eşleşiyor, minor fark kontrol et
            chrome_parts = chrome_ver.split('.')
            cached_parts = cached_ver.split('.')
            if len(chrome_parts) >= 3 and len(cached_parts) >= 3:
                # İlk 3 parça eşleşiyorsa sorun yok
                if chrome_parts[:3] == cached_parts[:3]:
                    print(f"  ✅ ChromeDriver uyumlu (Chrome {chrome_ver}, Driver {cached_ver})")
                    return
                else:
                    print(f"  ⚠️  ChromeDriver minor uyumsuzluk: Chrome {chrome_ver} vs Driver {cached_ver}")
            else:
                print(f"  ✅ ChromeDriver major uyumlu (Chrome {chrome_major}, Driver {cached_major})")
                return
        else:
            print(f"  ❌ ChromeDriver uyumsuz! Chrome {chrome_ver} vs Driver {cached_ver}")

        try:
            subprocess.run(['taskkill', '/f', '/im', 'chromedriver.exe'],
                           capture_output=True, timeout=5)
        except Exception:
            pass
        time.sleep(0.5)

        # Eski cache'i temizle
        import shutil
        try:
            shutil.rmtree(WDM_CACHE_DIR)
            print(f"  🧹 Eski ChromeDriver cache temizlendi ({cached_ver})")
        except Exception as e:
            print(f"  ⚠️  Cache temizleme hatası: {e}")
            # Dosya dosya silmeyi dene
            for root, dirs, files in os.walk(WDM_CACHE_DIR, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except Exception:
                        pass
    else:
        print(f"  ℹ️  ChromeDriver cache boş, ilk indirme yapılacak (Chrome {chrome_ver})")

    print(f"  🔄 ChromeDriver {chrome_major}.x indiriliyor (webdriver-manager)...")

# ══════════════════════════════════════════════════════════════════
# GEMINI TARAYICI KÖPRÜSÜ
# ══════════════════════════════════════════════════════════════════

class GeminiBridge:
    """Selenium ile Relay Ver 1.0'a sınırsız erişim."""

    def __init__(self, headless: bool = False):
        self.driver = None
        self._lock = threading.RLock()  # Reentrant — agent tool loop için
        self._ready = False
        self._last_response_count = 0
        self._headless = headless
        self._request_count = 0  # İlk istekte new chat atla
        self._keepalive_timer = None
        self._recovering = False  # Arka plan recovery devam ediyor mu?

    def _start_keepalive(self):
        """Her 10 saniyede bir driver'a aktif ping atarak bağlantıyı canlı tut."""
        def _ping():
            if self.driver and self._ready:
                try:
                    self.driver.execute_script("return document.readyState;")
                except Exception as e:
                    # Session kopmuş — hemen arka planda recovery başlat
                    self._ready = False
                    print(f"  ⚠️ Keepalive: bağlantı koptu, arka planda recovery başlatılıyor...")
                    recovery_thread = threading.Thread(target=self._background_recovery, daemon=True)
                    recovery_thread.start()
                    return  # Timer'ı yeniden kurma
            # Tekrar zamanlayıcıyı kur
            if self._ready:
                self._keepalive_timer = threading.Timer(10, _ping)
                self._keepalive_timer.daemon = True
                self._keepalive_timer.start()

        if self._keepalive_timer:
            self._keepalive_timer.cancel()
        self._keepalive_timer = threading.Timer(10, _ping)
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _background_recovery(self):
        """Arka planda tarayıcıyı yeniden başlat — kullanıcı isteği beklemesin."""
        self._recovering = True
        try:
            with self._lock:
                if self._ready:  # Başka bir thread zaten kurtarmışsa çık
                    return
                print("  🔄 Arka plan recovery: tarayıcı yeniden başlatılıyor...")
                if self.start():
                    print("  ✅ Arka plan recovery başarılı — Relay hazır!")
                else:
                    print("  ❌ Arka plan recovery başarısız, sonraki istekte tekrar denenecek.")
        except Exception as e:
            print(f"  ❌ Arka plan recovery hatası: {e}")
        finally:
            self._recovering = False

    def _hide_from_taskbar(self):
        """Windows API ile SADECE Gemini Chrome'u taskbar'dan gizle.
        NOT: VS Code da Chromium tabanlı — tüm 'Chrome' pencerelerini hedeflemek
        VS Code'u da gizler! Sadece chrome_profile_gemini kullanan süreçleri hedefle."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            SW_HIDE = 0
            SW_SHOW = 5

            # Sadece chrome_profile_gemini kullanan Chrome PID'lerini bul
            gemini_pids = set()
            try:
                result = subprocess.run(
                    ['powershell', '-NoProfile', '-Command',
                     "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                     "Where-Object { $_.CommandLine -like '*chrome_profile_gemini*' } | "
                     "Select-Object -ExpandProperty ProcessId"],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.strip().split('\n'):
                    pid = line.strip()
                    if pid.isdigit():
                        gemini_pids.add(int(pid))
            except Exception:
                pass

            if not gemini_pids:
                print("  ⚠️  Gemini Chrome PID bulunamadı, taskbar gizleme atlanıyor")
                return

            # EnumWindows ile SADECE Gemini Chrome pencerelerini bul (PID bazlı filtre)
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            chrome_hwnds = []

            def enum_callback(h, lParam):
                if user32.IsWindowVisible(h):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    if pid.value in gemini_pids:
                        chrome_hwnds.append(h)
                return True

            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

            for h in chrome_hwnds:
                # Pencereyi gizle, stil değiştir, geri göster (ama ekran dışında)
                user32.ShowWindow(h, SW_HIDE)
                style = user32.GetWindowLongW(h, GWL_EXSTYLE)
                style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
                user32.SetWindowLongW(h, GWL_EXSTYLE, style)
                user32.ShowWindow(h, SW_SHOW)
                # Tekrar ekran dışına taşı
                user32.SetWindowPos(h, None, -32000, -32000, 0, 0, 0x0001 | 0x0004 | 0x0010)

            if chrome_hwnds:
                print(f"  👻 Tarayıcı taskbar'dan gizlendi ({len(chrome_hwnds)} pencere)")
        except Exception as e:
            print(f"  ⚠️  Taskbar gizleme başarısız: {e}")

    def _is_driver_alive(self) -> bool:
        """Mevcut driver hâlâ çalışıyor mu? (max 5sn timeout)"""
        if not self.driver:
            return False
        result = [False]
        def check():
            try:
                _ = self.driver.current_url
                result[0] = True
            except Exception:
                pass
        t = threading.Thread(target=check, daemon=True)
        t.start()
        t.join(timeout=5)
        return result[0]

    def start(self) -> bool:
        """Chrome'u Relay Ver 1.0 ile başlat."""
        print("🌐 Gemini tarayıcısı başlatılıyor...")

        # Mevcut driver varsa önce onu temiz kapat
        if self.driver:
            print("  🔄 Mevcut tarayıcı oturumu kapatılıyor...")
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._ready = False
            time.sleep(1)

        # Kilit dosyaları VE eski Gemini Chrome süreçlerini temizle
        self._kill_gemini_chrome()
        self._cleanup_lock_files()
        time.sleep(2)

        # Profil cache temizle (önceki crash'lerden bozuk kalabilir)
        import shutil
        for cache_dir in ["Cache", "Code Cache", "GPUCache", "DawnCache", "ShaderCache", "GraphiteDawnCache", "GrShaderCache"]:
            cache_path = os.path.join(GEMINI_PROFILE, "Default", cache_dir)
            if os.path.exists(cache_path):
                try:
                    shutil.rmtree(cache_path, ignore_errors=True)
                except Exception:
                    pass

        # Chrome-ChromeDriver versiyon uyumunu kontrol et ve gerekirse güncelle
        _ensure_chromedriver_compatible()

        options = Options()
        options.add_argument(f"--user-data-dir={GEMINI_PROFILE}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-crash-reporter")
        options.add_argument("--disable-in-process-stack-traces")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        if self._headless:
            # Headless yerine pencereyi ekran dışına taşı (Gemini headless tespit ediyor)
            options.add_argument("--window-size=900,700")
            options.add_argument("--window-position=-32000,-32000")
            options.add_argument("--start-minimized")
        else:
            options.add_argument("--window-size=900,700")
            options.add_argument("--window-position=50,50")

        try:
            service = Service(ChromeDriverManager().install())
            try:
                self.driver = webdriver.Chrome(service=service, options=options)
            except Exception as e:
                err_msg = str(e).lower()
                # Profil kilitli olabilir
                if "user data directory" in err_msg or "already running" in err_msg or "cannot create" in err_msg:
                    print("  ⚠️ Profil kilitli, eski Chrome temizleniyor...")
                    self._kill_gemini_chrome()
                    time.sleep(2)
                    self._cleanup_lock_files()
                    self.driver = webdriver.Chrome(service=service, options=options)
                # Session hatası (profil kilitli veya ChromeDriver uyumsuz)
                elif "session not created" in err_msg or "chrome instance exited" in err_msg or "this version of chromedriver" in err_msg:
                    print("  ⚠️ Session oluşturulamadı, tam temizlik yapılıyor...")
                    # 1. Eski Gemini Chrome süreçlerini öldür
                    self._kill_gemini_chrome()
                    # 2. ChromeDriver süreçlerini öldür
                    try:
                        subprocess.run(['taskkill', '/f', '/im', 'chromedriver.exe'],
                                       capture_output=True, timeout=5)
                    except Exception:
                        pass
                    time.sleep(2)
                    # 3. Kilit dosyalarını temizle
                    self._cleanup_lock_files()
                    time.sleep(1)
                    # 4. Aynı driver ile tekrar dene
                    try:
                        self.driver = webdriver.Chrome(service=service, options=options)
                    except Exception:
                        # 5. Son çare: ChromeDriver cache temizle, yeniden indir
                        print("  ⚠️ Hâlâ başarısız, ChromeDriver cache temizleniyor...")
                        import shutil
                        try:
                            shutil.rmtree(WDM_CACHE_DIR, ignore_errors=True)
                        except Exception:
                            pass
                        time.sleep(1)
                        service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    raise
            # Bot tespit önleme
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    delete navigator.__proto__.webdriver;
                """
            })
            self.driver.get(GEMINI_URL)
            print(f"  ✅ Gemini açıldı: {GEMINI_URL}")

            print("  ⏳ Sayfa yükleniyor...")
            time.sleep(5)

            # Sayfa yüklenirken Chrome çökebilir — kontrol et
            if not self._is_driver_alive():
                print("  ⚠️ Chrome sayfa yüklerken çöktü")
                return False

            # Login kontrolü
            if "accounts.google.com" in self.driver.current_url:
                if self._headless:
                    # Pencereyi görünür yap - login için
                    print("\n  ⚠️  GOOGLE GİRİŞİ GEREKLİ! Tarayıcı penceresi gösteriliyor...")
                    try:
                        self.driver.set_window_position(50, 50)
                        self.driver.set_window_size(900, 700)
                    except Exception:
                        pass
                print("\n  ⚠️  GOOGLE GİRİŞİ GEREKLİ!")
                print("  → Açılan tarayıcıda Google hesabınıza giriş yapın")
                print("  → Giriş yapıldıktan sonra otomatik devam edecek...\n")
                # Giriş yapılana kadar bekle (max 5 dakika)
                for _ in range(300):
                    time.sleep(1)
                    if "gemini.google.com" in self.driver.current_url:
                        print("  ✅ Giriş başarılı!")
                        # Login sonrası tekrar gizle
                        if self._headless:
                            try:
                                self.driver.set_window_position(-32000, -32000)
                                self.driver.minimize_window()
                            except Exception:
                                pass
                        time.sleep(3)
                        break
                else:
                    print("  ❌ Giriş zaman aşımı!")
                    return False

            # Input alanını kontrol et
            time.sleep(2)
            input_area = self._find_input_area()
            if input_area:
                self._ready = True
                self._last_response_count = len(self._get_response_elements())
                self._start_keepalive()
                # Sayfa hazır — şimdi güvenle taskbar'dan gizle
                if self._headless:
                    self._hide_from_taskbar()
                print("  ✅ Gemini hazır - soru bekleniyor!")
                return True
            else:
                print("  ⚠️  Input alanı bulunamadı, 10 saniye daha bekleniyor...")
                time.sleep(10)
                input_area = self._find_input_area()
                if input_area:
                    self._ready = True
                    self._last_response_count = len(self._get_response_elements())
                    self._start_keepalive()
                    if self._headless:
                        self._hide_from_taskbar()
                    print("  ✅ Gemini hazır!")
                    return True
                print("  ❌ Gemini input alanı bulunamadı!")
                return False

        except Exception as e:
            print(f"  ❌ Tarayıcı hatası: {e}")
            return False

    def ask(self, question: str, timeout: int = 300, new_chat: bool = True) -> str:
        """Gemini'ye soru sor, cevap al. new_chat=False ise aynı sohbette devam eder."""
        # Arka plan recovery devam ediyorsa bitmesini bekle (max 30sn)
        if self._recovering:
            print("  ⏳ Arka plan recovery devam ediyor, bekleniyor...")
            for _ in range(60):
                time.sleep(0.5)
                if not self._recovering:
                    break
            if self._recovering:
                print("  ⚠️ Recovery zaman aşımı")

        with self._lock:
            if not self._ready or not self._is_driver_alive():
                # Önce basit recovery dene (refresh)
                if self.driver and self._is_driver_alive():
                    print("  ⚠️ Session hazır değil, sayfa yenileniyor...")
                    try:
                        self.driver.get(GEMINI_URL)
                        time.sleep(5)
                        if self._find_input_area():
                            self._ready = True
                            self._last_response_count = len(self._get_response_elements())
                            print("  ✅ Session kurtarıldı!")
                        else:
                            raise Exception("Input bulunamadı")
                    except Exception:
                        print("  ⚠️ Basit recovery başarısız, tam yeniden başlatma...")
                        if not self.start():
                            return "❌ Gemini tarayıcısı yeniden başlatılamadı"
                else:
                    print("  ⚠️ Tarayıcı bağlantısı kopmuş, yeniden başlatılıyor...")
                    if not self.start():
                        return "❌ Gemini tarayıcısı yeniden başlatılamadı"

            try:
                # İlk istekte new chat açmaya çalışma (sayfa zaten temiz)
                self._request_count += 1
                if new_chat and self._request_count > 1:
                    self._try_new_chat()

                # Input alanını bul
                input_area = self._find_input_area()
                if not input_area:
                    print("  🔍 Input bulunamadı, sayfayı yeniliyorum...")
                    try:
                        self.driver.refresh()
                        time.sleep(4)
                    except Exception as e:
                        print(f"  ⚠️ Refresh hatası: {e}")
                        # Sadece Gemini URL'ye tekrar git, start() çağırma
                        try:
                            self.driver.get(GEMINI_URL)
                            time.sleep(5)
                        except Exception:
                            return "❌ Gemini sayfası yüklenemedi"
                    input_area = self._find_input_area()
                    if not input_area:
                        # Debug: Sayfadaki tüm contenteditable ve textarea'ları listele
                        self._debug_page_elements()
                        return "❌ Gemini input alanı bulunamadı"

                print(f"  🔍 Input bulundu: tag={input_area.tag_name}, class={input_area.get_attribute('class')[:50] if input_area.get_attribute('class') else 'N/A'}")

                # Mevcut cevap sayısını kaydet
                initial_count = len(self._get_response_elements())
                print(f"  🔍 Mevcut cevap sayısı: {initial_count}")

                # Input alanını temizle (WhatsApp bot'taki gibi)
                try:
                    input_area.click()
                    time.sleep(0.1)
                    input_area.send_keys(Keys.CONTROL + "a")
                    input_area.send_keys(Keys.DELETE)
                    time.sleep(0.1)
                except Exception:
                    pass

                # Soruyu yaz (JavaScript ile - newline sorunu yok)
                # Büyük metinler için parça parça yaz (browser donmasını önle)
                CHUNK_SIZE = 30_000  # 30K karakter parçalar halinde
                if len(question) > CHUNK_SIZE:
                    print(f"  📝 Büyük prompt ({len(question):,} chr), parça parça yazılıyor...")
                    self.driver.execute_script("""
                        var el = arguments[0];
                        el.focus();
                        el.innerText = '';
                    """, input_area)
                    for i in range(0, len(question), CHUNK_SIZE):
                        chunk = question[i:i+CHUNK_SIZE]
                        self.driver.execute_script("""
                            var el = arguments[0];
                            var chunk = arguments[1];
                            el.innerText += chunk;
                        """, input_area, chunk)
                        time.sleep(0.1)
                    self.driver.execute_script("""
                        var el = arguments[0];
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, input_area)
                else:
                    self.driver.execute_script("""
                        var el = arguments[0];
                        var text = arguments[1];
                        el.focus();
                        el.innerText = text;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, input_area, question)
                time.sleep(0.2)

                # Input'a metin girdi mi kontrol et
                typed_text = input_area.text or input_area.get_attribute("innerText") or ""
                print(f"  🔍 Input'a yazılan: {typed_text[:50]}..." if len(typed_text) > 50 else f"  🔍 Input'a yazılan: {typed_text}")

                # Gönder butonuna bas
                send_btn = self._find_send_button()
                if send_btn:
                    print(f"  🔍 Gönder butonu bulundu: aria-label={send_btn.get_attribute('aria-label')}")
                    try:
                        send_btn.click()
                        print("  🔍 Gönder butonuna tıklandı (click)")
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", send_btn)
                        print("  🔍 Gönder butonuna tıklandı (JS click)")
                else:
                    print("  🔍 Gönder butonu bulunamadı, Enter basılıyor...")
                    # XPath ile dene
                    sent = False
                    xpath_selectors = [
                        '//button[contains(@aria-label, "Send")]',
                        '//button[contains(@aria-label, "send")]',
                        '//button[contains(@aria-label, "Gönder")]',
                        '//button[.//mat-icon[contains(text(), "send")]]',
                        '//button[.//span[contains(text(), "send")]]',
                    ]
                    for xp in xpath_selectors:
                        try:
                            els = self.driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed() and el.is_enabled():
                                    el.click()
                                    print(f"  🔍 XPath ile gönderildi: {xp}")
                                    sent = True
                                    break
                        except Exception:
                            continue
                        if sent:
                            break
                    if not sent:
                        input_area.send_keys(Keys.RETURN)
                        print("  🔍 Enter ile gönderildi")

                time.sleep(0.3)

                # Cevabı bekle
                response = self._wait_for_response(initial_count, timeout)
                if response:
                    self._last_response_count = len(self._get_response_elements())
                    return response
                else:
                    # Debug: Sayfadaki response elementlerini göster
                    self._debug_response_elements()
                    return "❌ Gemini cevap vermedi (timeout)"

            except Exception as e:
                import traceback
                traceback.print_exc()
                return f"❌ Gemini hatası: {e}"

    def _debug_page_elements(self):
        """Sayfadaki input olabilecek elementleri listele."""
        try:
            elements = self.driver.execute_script("""
                var results = [];
                var editables = document.querySelectorAll('[contenteditable="true"]');
                editables.forEach(function(el) {
                    results.push('contenteditable: tag=' + el.tagName + ' class=' + el.className.substring(0,60) + ' visible=' + (el.offsetHeight > 0));
                });
                var textareas = document.querySelectorAll('textarea');
                textareas.forEach(function(el) {
                    results.push('textarea: placeholder=' + (el.placeholder || 'N/A').substring(0,40) + ' visible=' + (el.offsetHeight > 0));
                });
                return results;
            """)
            print("  🔍 DEBUG - Sayfadaki elementler:")
            for el in (elements or []):
                print(f"    → {el}")
        except Exception as e:
            print(f"  🔍 DEBUG hata: {e}")

    def _debug_response_elements(self):
        """Sayfadaki response elementlerini debug et."""
        try:
            info = self.driver.execute_script("""
                var results = [];
                var selectors = [
                    'message-content', 'model-response', '.response-container',
                    '.markdown', '[class*="response"]', '[class*="message-content"]',
                    'message-content .markdown', '.model-response-text',
                    '.turn-content', '.response-text', '.gemini-response'
                ];
                selectors.forEach(function(sel) {
                    try {
                        var els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            results.push(sel + ': ' + els.length + ' adet, son=' + (els[els.length-1].innerText || '').substring(0,60));
                        }
                    } catch(e) {}
                });
                // Ayrıca sayfa title ve URL
                results.push('URL: ' + window.location.href);
                results.push('Title: ' + document.title);
                return results;
            """)
            print("  🔍 DEBUG - Response elementleri:")
            for info_item in (info or []):
                print(f"    → {info_item}")
        except Exception as e:
            print(f"  🔍 DEBUG hata: {e}")

    def _try_new_chat(self):
        """Gemini'de yeni sohbet açmayı dene."""
        try:
            # "New chat" butonunu ara
            new_chat_selectors = [
                'a[href="/app"]',
                'button[aria-label*="New chat"]',
                'button[aria-label*="Yeni sohbet"]',
                'a[data-mat-icon-name="add"]',
            ]
            for sel in new_chat_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elements:
                        if el.is_displayed():
                            el.click()
                            time.sleep(1)
                            return
                except Exception:
                    continue
            
            # Fallback: URL'ye git
            if "/app/" in self.driver.current_url and self.driver.current_url != GEMINI_URL:
                self.driver.get(GEMINI_URL)
                time.sleep(2)
        except Exception:
            pass

    def _find_input_area(self):
        """Gemini input alanını bul."""
        selectors = [
            'div.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][aria-label*="prompt"]',
            'div[contenteditable="true"][aria-label*="Enter"]',
            'div[contenteditable="true"][role="textbox"]',
            '.input-area div[contenteditable="true"]',
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"]',
            'textarea[aria-label*="prompt"]',
            'textarea[placeholder*="Enter"]',
            'textarea[aria-label*="Enter"]',
        ]
        for sel in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _find_send_button(self):
        """Gönder butonunu bul."""
        selectors = [
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
            'button[aria-label*="send"]',
            'button[data-at="send"]',
            'button.send-button:not(.stop)',
            'button mat-icon[fonticon="send"]',
        ]
        for sel in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        # Stop butonu değilse
                        aria = (el.get_attribute("aria-label") or "").lower()
                        if "stop" not in aria and "dur" not in aria:
                            return el
            except Exception:
                continue
        return None

    def _get_response_elements(self):
        """Gemini cevap elementlerini bul."""
        selectors = [
            'message-content .markdown',
            '.response-container .markdown',
            '.model-response-text',
            'model-response .markdown',
            '.response-content',
            'message-content',
            '.conversation-container model-response',
        ]
        for sel in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    return elements
            except Exception:
                continue

        # JS fallback
        try:
            elements = self.driver.execute_script("""
                var candidates = document.querySelectorAll(
                    'message-content, model-response, .response-container'
                );
                var results = [];
                candidates.forEach(function(el) {
                    if (el.innerText && el.innerText.trim().length > 5) {
                        results.push(el);
                    }
                });
                return results;
            """)
            return elements or []
        except Exception:
            return []

    def _is_generating(self) -> bool:
        """Gemini hâlâ cevap yazıyor mu?"""
        try:
            indicators = [
                '[class*="loading"]',
                '[class*="thinking"]',
                '[class*="generating"]',
                '.loading-indicator',
                'mat-progress-bar',
                '.response-streaming',
                '[data-is-streaming="true"]',
                'button.send-button.stop',
            ]
            for sel in indicators:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elements:
                        if el.is_displayed():
                            return True
                except Exception:
                    continue

            is_busy = self.driver.execute_script("""
                var streamEl = document.querySelector('[data-is-streaming], .response-streaming');
                if (streamEl) return true;
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var label = (btns[i].getAttribute('aria-label') || '').toLowerCase();
                    if (label.indexOf('stop') >= 0 && btns[i].offsetHeight > 0) return true;
                }
                return false;
            """)
            return bool(is_busy)
        except Exception:
            return False

    def _extract_clean_text(self, element) -> str:
        """Response elementinden temiz metin al (UI butonlarını çıkar)."""
        try:
            # JavaScript ile sadece markdown içeriğini al, buton/etiketleri atla
            text = self.driver.execute_script("""
                var el = arguments[0];
                // Önce markdown class'ı içindeki metni dene
                var md = el.querySelector('.markdown-main-panel') || el.querySelector('.markdown') || el;
                // Clone edip gereksiz elementleri çıkar
                var clone = md.cloneNode(true);
                // Butonları, toolbar'ı, code header'ını kaldır
                var removeSelectors = [
                    'button', '.code-block-decoration', '.code-block-header',
                    '.snippet-label', '.copy-button', '.action-bar',
                    '.toolbar', '[role="toolbar"]', '.overflow-menu',
                    'mat-icon', '.header-row', '.code-block-info'
                ];
                removeSelectors.forEach(function(sel) {
                    clone.querySelectorAll(sel).forEach(function(e) { e.remove(); });
                });
                return clone.innerText || clone.textContent || '';
            """, element)
            return (text or "").strip()
        except Exception:
            # Fallback: düz .text
            return (element.text or "").strip()

    def _wait_for_response(self, initial_count: int, timeout: int) -> str:
        """Gemini cevabını bekle."""
        start_time = time.time()
        last_text = ""
        stable_count = 0

        while time.time() - start_time < timeout:
            try:
                responses = self._get_response_elements()
                if len(responses) > initial_count:
                    latest = responses[-1]
                    current_text = self._extract_clean_text(latest)

                    if self._is_generating():
                        last_text = current_text
                        stable_count = 0
                        time.sleep(0.3)
                        continue

                    if current_text and current_text == last_text and len(current_text) >= 1:
                        stable_count += 1
                        if stable_count >= 3:
                            return current_text
                    else:
                        last_text = current_text
                        stable_count = 0

                time.sleep(0.25)
            except Exception:
                time.sleep(0.25)

        # Timeout durumunda son metni döndür
        if last_text:
            return last_text
        return None

    def _cleanup_lock_files(self):
        """Sadece Chrome kilit dosyalarını temizle (süreç öldürme YOK)."""
        profile_dir = os.path.abspath(GEMINI_PROFILE)
        for lock_file in ["lockfile", "SingletonLock"]:
            lock_path = os.path.join(profile_dir, lock_file)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
        default_lock = os.path.join(profile_dir, "Default", "Lock")
        if os.path.exists(default_lock):
            try:
                os.remove(default_lock)
            except Exception:
                pass

    def _kill_gemini_chrome(self):
        """SADECE chrome_profile_gemini kullanan Chrome süreçlerini öldür.
        Normal kullanıcı Chrome'larına dokunmaz."""
        try:
            # 1) chrome_profile_gemini içeren TÜM Chrome süreçlerini bul
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*chrome_profile_gemini*' } | "
                 "Select-Object -ExpandProperty ProcessId"],
                capture_output=True, text=True, timeout=10
            )
            gemini_pids = set()
            for line in result.stdout.strip().split('\n'):
                pid = line.strip()
                if pid.isdigit():
                    gemini_pids.add(int(pid))

            # 2) Bu PID'lerin parent'larını da bul (ana Chrome süreci profil bilgisi taşımayabilir)
            if gemini_pids:
                result2 = subprocess.run(
                    ['powershell', '-NoProfile', '-Command',
                     "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                     "Select-Object ProcessId, ParentProcessId | ConvertTo-Csv -NoTypeInformation"],
                    capture_output=True, text=True, timeout=10
                )
                all_chrome = {}
                for line in result2.stdout.strip().split('\n')[1:]:  # CSV header atla
                    parts = line.strip().strip('"').split('","')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        all_chrome[int(parts[0])] = int(parts[1])

                # Parent'ı bir Gemini Chrome olan süreçleri de ekle
                for pid, ppid in all_chrome.items():
                    if ppid in gemini_pids:
                        gemini_pids.add(pid)
                # Gemini Chrome'ların child'ı olan parent'ları da bul
                # (ana süreç profil bilgisi taşımayabilir ama child'ları taşır)
                for pid, ppid in all_chrome.items():
                    if pid in gemini_pids and ppid in all_chrome:
                        gemini_pids.add(ppid)

            # 3) Sadece Gemini Chrome'ları öldür
            killed = 0
            for pid in gemini_pids:
                try:
                    subprocess.run(['taskkill', '/f', '/pid', str(pid)],
                                   capture_output=True, timeout=5)
                    killed += 1
                except Exception:
                    pass
            if killed:
                print(f"  🧹 {killed} eski Chrome süreci temizlendi")

            # 4) Eski ChromeDriver süreçlerini de öldür
            try:
                subprocess.run(['taskkill', '/f', '/im', 'chromedriver.exe'],
                               capture_output=True, timeout=5)
            except Exception:
                pass
        except Exception:
            pass

    def stop(self):
        """Tarayıcıyı kapat."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self._ready = False
        print("🛑 Gemini tarayıcısı kapatıldı")


# ══════════════════════════════════════════════════════════════════
# WORKSPACE FILE TREE — Gemini'ye workspace bilgisi ver
# ══════════════════════════════════════════════════════════════════

_workspace_tree_cache: str = ""
_workspace_tree_time: float = 0

def _get_workspace_tree(max_depth: int = 2, max_entries: int = 80) -> str:
    """Workspace dosya ağacını oluştur. Gemini'nin dosya yapısını bilmesi için."""
    global _workspace_tree_cache, _workspace_tree_time
    # 30 saniye cache — dosya ağacı sık değişmez
    if _workspace_tree_cache and (time.time() - _workspace_tree_time) < 30:
        return _workspace_tree_cache

    skip_dirs = {'__pycache__', '.git', 'node_modules', '.venv', 'venv',
                 'build', 'dist', '.tox', '.mypy_cache', '.pytest_cache',
                 'chrome_profile', 'chrome_profile_gemini', 'Bark',
                 'hubert_models', 'silero_models', 'piper_models', 'ffmpeg',
                 'chrome_profile_gemini', 'Headless_output', 'whatsapp_downloads',
                 'output', 'data', 'ai_data', 'memory'}

    entries = []

    def _walk(dir_path, prefix, depth):
        if depth > max_depth or len(entries) >= max_entries:
            return
        try:
            items = sorted(os.listdir(dir_path))
        except OSError:
            return

        dirs_list = []
        files_list = []
        for item in items:
            full = os.path.join(dir_path, item)
            if os.path.isdir(full):
                if item not in skip_dirs and not item.startswith('.'):
                    dirs_list.append(item)
            else:
                files_list.append(item)

        # Dosyaları göster
        for f in files_list:
            if len(entries) >= max_entries:
                return
            entries.append(f"{prefix}{f}")

        # Alt klasörleri göster
        for d in dirs_list:
            if len(entries) >= max_entries:
                return
            entries.append(f"{prefix}{d}/")
            _walk(os.path.join(dir_path, d), prefix + "  ", depth + 1)

    _walk(BASE_DIR, "", 0)

    if entries:
        tree = "📁 WORKSPACE DOSYA AĞACI:\n" + "\n".join(entries)
        if len(entries) >= max_entries:
            tree += f"\n... (toplam {max_entries}+ dosya/klasör)"
    else:
        tree = "📁 WORKSPACE BOŞ"

    _workspace_tree_cache = tree
    _workspace_tree_time = time.time()
    return tree


# ══════════════════════════════════════════════════════════════════
# OPENAI UYUMLU HTTP SUNUCU
# ══════════════════════════════════════════════════════════════════

gemini_bridge: GeminiBridge = None


class OpenAIHandler(BaseHTTPRequestHandler):
    """OpenAI API formatında istekleri karşılar, Gemini'ye yönlendirir."""

    def log_message(self, format, *args):
        """İstek loglarını göster."""
        print(f"  📨 {args[0]}")

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        """GET istekleri — model listesi vs."""
        if self.path == "/v1/models" or self.path == "/api/tags":
            # Model listesi (Ollama & OpenAI formatı)
            # context_length büyük olmalı ki Continue tüm workspace dosyalarını göndersin
            models = {
                "object": "list",
                "data": [
                    {
                        "id": "relay-v1",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "google",
                        "context_length": 1_000_000,
                        "max_model_len": 1_000_000,
                    }
                ],
                "models": [
                    {
                        "name": "relay-v1",
                        "model": "relay-v1",
                        "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "size": 0,
                        "details": {
                            "parameter_size": "unknown",
                            "context_length": 1_000_000,
                        },
                    }
                ],
            }
            self._json_response(200, models)
        elif self.path == "/":
            self._json_response(200, {
                "status": "ok",
                "service": "Relay Ver 1.0 Proxy",
                "model": "relay-v1 (Selenium)",
                "ready": gemini_bridge._ready if gemini_bridge else False,
            })
        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        """POST istekleri — chat completion."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 50_000_000:  # 50MB limit (büyük codebase desteklemek için)
            self._json_response(413, {"error": "Request too large"})
            return
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._json_response(400, {"error": "Invalid JSON"})
            return

        # /v1/chat/completions (OpenAI format)
        # /api/chat (Ollama format)
        if self.path in ("/v1/chat/completions", "/api/chat", "/chat/completions"):
            self._handle_chat(data)
        elif self.path == "/api/generate":
            self._handle_generate(data)
        else:
            self._json_response(404, {"error": "Not found"})

    def _handle_chat(self, data: dict):
        """Chat completion isteğini işle — AGENT LOOP ile yerel araç yürütme."""
        # Continue'dan gelen tool tanımlarını çıkar (proxy kendi araçlarını kullanır)
        data.pop("tools", None)
        data.pop("tool_choice", None)
        data.pop("functions", None)
        data.pop("function_call", None)

        messages = data.get("messages", [])
        if not messages:
            self._json_response(400, {"error": "messages required"})
            return

        # Her yeni istek başında tool cache'i temizle
        LocalToolExecutor.clear_cache()

        # Mesajları filtrele
        filtered_messages = self._filter_messages(messages)

        # ═══ PROMPT OLUŞTURMA ═══
        prompt_parts = []

        # Kullanıcı mesajını ayıkla
        user_text_lower = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                if isinstance(c, list):
                    c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                user_text_lower = c.lower().strip()
                break
        identity_prompt = RELAY_IDENTITY_PROMPT.format(workspace_dir=BASE_DIR)
        tool_rules = RELAY_TOOL_RULES.format(workspace_dir=BASE_DIR)
        prompt_parts.append(f"[System Instruction]: {identity_prompt}\n{tool_rules}")
        tool_prompt = self._build_tool_prompt(LocalToolExecutor.TOOL_DEFINITIONS)
        prompt_parts.append(f"[System Instruction]: {tool_prompt}")

        # Workspace dosya ağacını ekle — Gemini hangi dosyaların olduğunu bilsin
        workspace_tree = _get_workspace_tree()
        prompt_parts.append(f"[Workspace Bilgisi]: {workspace_tree}")

        # 3) Kullanıcı mesajları
        for msg in filtered_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = "\n".join(text_parts)
            if role == "system":
                if content:
                    prompt_parts.append(f"[System Instruction]: {content}")
            elif role == "user":
                if content:
                    prompt_parts.append(content)
            elif role == "assistant":
                tool_calls_in_msg = msg.get("tool_calls", [])
                if tool_calls_in_msg:
                    tc_texts = []
                    for tc in tool_calls_in_msg:
                        func = tc.get("function", {})
                        tc_texts.append(f'{func.get("name", "")}({func.get("arguments", "")})')
                    prompt_parts.append(f"[Previous Tool Call]: {'; '.join(tc_texts)}")
                elif content:
                    prompt_parts.append(f"[Previous AI Response]: {content}")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                prompt_parts.append(f"[Tool Result - {tool_name}]: {content}")

        full_prompt = "\n\n".join(prompt_parts)

        # Prompt uzunluk limiti
        MAX_PROMPT_CHARS = 80_000
        if len(full_prompt) > MAX_PROMPT_CHARS:
            print(f"  ⚠️  Prompt çok uzun ({len(full_prompt):,} chr), kırpılıyor...")
            head = full_prompt[:20_000]
            tail = full_prompt[-(MAX_PROMPT_CHARS - 20_000):]
            full_prompt = head + "\n\n[... ortadaki kısım uzunluk nedeniyle kırpıldı ...]\n\n" + tail

        print(f"  💬 Soru ({len(full_prompt):,} chr): {full_prompt[:80]}...")
        start = time.time()

        # Kullanıcı sorusunu ayıkla (iterasyonlarda tekrar kullanmak için)
        user_question = ""
        for msg in reversed(filtered_messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    content = "\n".join(text_parts)
                user_question = content
                break

        # System ve tool prompt'ları kaydet (iterasyonlarda tekrar kullanılacak)
        relay_prompt = RELAY_IDENTITY_PROMPT.format(workspace_dir=BASE_DIR) + "\n" + RELAY_TOOL_RULES.format(workspace_dir=BASE_DIR)
        tool_prompt_text = self._build_tool_prompt(LocalToolExecutor.TOOL_DEFINITIONS)

        # ═══ AGENT LOOP — Her zaman araç erişimli çalış ═══
        # Gemini araç gerekmediğini kendisi anlar → ilk iterasyonda cevap verir.
        # Sohbet için ayrı dal KALDIRDIK — keyword bakımı sürdürülemezdi.
        MAX_TOOL_ITERATIONS = 5  # analyze_file ile 2-3 iterasyon yeterli
        GEMINI_MAX_RETRIES = 2   # Gemini boş/hata dönerse tekrar dene
        final_response = ""
        current_prompt = full_prompt
        total_tool_calls = 0
        all_tool_results = []  # Tüm iterasyonların araç sonuçlarını biriktir

        for iteration in range(MAX_TOOL_ITERATIONS + 1):
            # ═══ GEMİNİ ÇAĞRISI — retry ile ═══
            response_text = None
            for retry in range(GEMINI_MAX_RETRIES + 1):
                response_text = gemini_bridge.ask(current_prompt)
                if response_text and not response_text.startswith("❌"):
                    break
                if retry < GEMINI_MAX_RETRIES:
                    wait_sec = (retry + 1) * 2
                    print(f"  ⚠️  Gemini boş/hata döndü, {wait_sec}s bekleyip tekrar deneniyor... (deneme {retry + 2}/{GEMINI_MAX_RETRIES + 1})")
                    time.sleep(wait_sec)

            if not response_text:
                final_response = "Gemini cevap veremedi. Lütfen tekrar deneyin."
                break

            # Tool call parse et
            tool_calls_parsed = self._parse_tool_calls(response_text)

            if not tool_calls_parsed:
                # İlk iterasyonda araç kullanmadı — dosya/kod sorusuysa dürt (nudge)
                if iteration == 0 and response_text:
                    # Dosya adı geçiyor mu? (güçlü sinyal)
                    file_match = re.search(r'[\w\-]+\.(?:py|js|ts|json|yaml|yml|md|txt|html|css|sh|bat|ps1|ipynb)', user_text_lower)
                    # veya önceki asistan mesajında araç kullanımı ima edilmiş mi?
                    prev_assistant_hinted = False
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant":
                            prev = str(msg.get("content", "")).lower()
                            if any(h in prev for h in ['.py', 'dosya', '```', 'fonksiyon', 'analiz', 'satır', 'settings']):
                                prev_assistant_hinted = True
                            break

                    if file_match or prev_assistant_hinted:
                        print(f"  ⚠️  Gemini araç kullanmadı, nudge yapılıyor...")
                        if file_match:
                            nudge = (
                                f"[System Instruction]: ÖNCEKİ CEVABIN YANLIŞ! Dosyayı bulmadan cevap verdin. "
                                f"MUTLAKA önce analyze_file veya list_dir aracını kullan!\n"
                                f"Dosya: {file_match.group(0)}\n"
                                f"Workspace: {BASE_DIR}\n\n"
                                f"[Kullanıcı Sorusu]: {user_question}\n\n"
                                f"[System Instruction]: {relay_prompt}\n{tool_prompt_text}\n\n"
                                f"HEMEN araç çağrısı yap, metin yazma!"
                            )
                        else:
                            nudge = (
                                f"[System Instruction]: Önceki konuşmada dosya/kod hakkında konuşulmuş. "
                                f"Kullanıcı sorusunu cevaplamak için MUTLAKA araç kullan!\n"
                                f"Workspace: {BASE_DIR}\n\n"
                                f"[Kullanıcı Sorusu]: {user_question}\n\n"
                                f"[System Instruction]: {relay_prompt}\n{tool_prompt_text}\n\n"
                                f"Araç çağrısı yap, sadece metin yazma!"
                            )
                        current_prompt = nudge
                        continue  # Bir iterasyon daha dene
                # Araç çağrısı yok → final cevap
                final_response = response_text
                break

            # ═══ ARAÇLARI YEREL OLARAK ÇALIŞTIR (PARALEL) ═══
            tool_names = [tc['function']['name'] for tc in tool_calls_parsed]
            print(f"  🔧 İterasyon {iteration + 1}: {tool_names} çalıştırılıyor{'(paralel)' if len(tool_calls_parsed) > 1 else ''}...")
            total_tool_calls += len(tool_calls_parsed)

            # Paralel çalıştır — okuma araçları eşzamanlı, yazma sıralı
            parallel_results = LocalToolExecutor.execute_parallel(tool_calls_parsed)
            for func_name, result in parallel_results:
                all_tool_results.append(f"[Araç Sonucu — {func_name}]:\n{result}")
                result_preview = result[:100].replace('\n', ' ')
                print(f"    ✅ {func_name} → {len(result):,} chr ({result_preview}...)")

                # ═══ AKILLI HATA KURTARMA ═══
                if 'bulunamadı' in result.lower() and func_name in ('read_file', 'analyze_file'):
                    # Dosya bulunamadı → otomatik file_search ile dosyayı bul
                    try:
                        # result'tan dosya adını çıkar
                        file_match = re.search(r'[\w\-./\\]+\.(?:py|js|ts|json|yaml|yml|md|txt|html|css)', result)
                        if file_match:
                            missing_file = os.path.basename(file_match.group(0))
                            print(f"    🔍 Dosya bulunamadı, file_search ile aranıyor: {missing_file}")
                            search_result = LocalToolExecutor.execute("file_search", {"query": f"**/{missing_file}"})
                            all_tool_results.append(f"[Araç Sonucu — file_search (otomatik)]:\n{search_result}")
                    except Exception:
                        pass

            # ═══ AKILLI PROMPT OLUŞTURMA ═══
            print(f"  📊 Toplam araç sonucu: {len(all_tool_results)}")

            # analyze_file var mı kontrol et — varsa zaten yapısal özet elimizde
            has_analysis = any('[Araç Sonucu — analyze_file]' in tr for tr in all_tool_results)

            # Son iterasyondaki sonuçları tam gönder, eskileri kısa tut
            recent_results = all_tool_results[-len(tool_calls_parsed):]
            old_results = all_tool_results[:-len(tool_calls_parsed)]

            summarized_old = []
            for old_r in old_results:
                if '[Araç Sonucu — read_file]' in old_r:
                    lines_list = old_r.split('\n')
                    header = lines_list[0] if lines_list else old_r[:80]
                    summarized_old.append(f"{header}\n[... içerik daha önce okundu ...]")
                elif any(f'[Araç Sonucu — {t}]' in old_r for t in ('grep_search', 'multi_grep')):
                    # Arama sonuçlarını kısa tut (ilk 10 eşleşme)
                    lines_list = old_r.split('\n')
                    header = lines_list[0] if lines_list else old_r[:80]
                    top_results = '\n'.join(lines_list[1:11]) if len(lines_list) > 1 else ''
                    summarized_old.append(f"{header}\n{top_results}\n[... daha fazla sonuç kısaltıldı ...]")
                elif any(f'[Araç Sonucu — {t}]' in old_r for t in ('analyze_file',)):
                    # Analiz sonuçlarını ilk 3000 chr ile sınırla
                    if len(old_r) > 3000:
                        summarized_old.append(old_r[:3000] + "\n[... analiz kısaltıldı ...]")
                    else:
                        summarized_old.append(old_r)
                else:
                    summarized_old.append(old_r)

            # Sonraki iterasyon promptu oluştur
            current_prompt = f"[System Instruction]: {relay_prompt}\n\n"
            current_prompt += f"[System Instruction]: {tool_prompt_text}\n\n"
            current_prompt += f"[Kullanıcı Sorusu]: {user_question}\n\n"

            if summarized_old:
                current_prompt += "[Önceki Araç Sonuçları - Özet]:\n"
                current_prompt += "\n\n".join(summarized_old)
                current_prompt += "\n\n"

            current_prompt += "[Son Araç Sonuçları - Tam]:\n"
            current_prompt += "\n\n".join(recent_results)

            # Yönerge
            if has_analysis:
                current_prompt += "\n\n✅ Dosya analizi tamamlandı. Şimdi araç sonuçlarını kullanarak kapsamlı Türkçe yanıt yaz."
                current_prompt += " Detaylı kod görmek istersen analyze_file sonuçlarındaki satır numaralarıyla read_file kullan."
            else:
                current_prompt += "\n\nAraç sonuçlarını kullanarak yanıt ver. Daha fazla bilgi gerekiyorsa araç çağrısı yap."

            # Prompt uzunluk kontrolü
            if len(current_prompt) > MAX_PROMPT_CHARS:
                print(f"  ⚠️  Prompt çok uzun ({len(current_prompt):,} chr), kırpılıyor...")
                head = current_prompt[:20_000]
                tail = current_prompt[-(MAX_PROMPT_CHARS - 20_000):]
                current_prompt = head + "\n\n[... kırpıldı ...]\n\n" + tail

            print(f"  🔄 İterasyon {iteration + 2} prompt: {len(current_prompt):,} chr ({len(all_tool_results)} araç sonucu)")

        else:
            # Max iterasyon aşıldı
            final_response = response_text if response_text else "Maksimum araç iterasyonu aşıldı."

        elapsed = time.time() - start
        iter_info = f", {total_tool_calls} araç" if total_tool_calls > 0 else ""

        # ═══ YANITTAN TOOL CALL ARTIKLARINI TEMİZLE ═══
        final_response = self._clean_tool_artifacts(final_response)

        print(f"  ✅ Cevap ({len(final_response):,} chr, {elapsed:.1f}s{iter_info})")

        # ═══ YANITI CONTINUE'A GÖNDER ═══
        stream = data.get("stream", False)

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self._cors_headers()
            self.end_headers()

            try:
                chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

                # ═══ GERÇEK STREAMING — kelime seviyesinde parçalar ═══
                # Cevabı kelime gruplarına böl, her birini SSE event olarak gönder
                CHUNK_SIZE = 8  # Her seferde ~8 kelime gönder
                words = final_response.split(' ')

                for i in range(0, len(words), CHUNK_SIZE):
                    chunk_words = words[i:i + CHUNK_SIZE]
                    chunk_text = ' '.join(chunk_words)
                    # İlk parça değilse başına boşluk ekle
                    if i > 0:
                        chunk_text = ' ' + chunk_text

                    chunk_data = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "relay-v1",
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk_text},
                            "finish_reason": None,
                        }],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                # Final chunk — stop
                done_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "relay-v1",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                self.wfile.write(f"data: {json.dumps(done_data)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (ConnectionAbortedError, BrokenPipeError, OSError) as e:
                print(f"  ⚠️  İstemci bağlantısı koptu: {e}")

            self.close_connection = True
        else:
            result = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "relay-v1",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": final_response},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": len(full_prompt) // 4,
                    "completion_tokens": len(final_response) // 4,
                    "total_tokens": (len(full_prompt) + len(final_response)) // 4,
                },
            }
            self._json_response(200, result)

    def _handle_generate(self, data: dict):
        """Ollama /api/generate formatı."""
        prompt = data.get("prompt", "")
        if not prompt:
            self._json_response(400, {"error": "prompt required"})
            return

        response_text = gemini_bridge.ask(prompt)

        # Tool call artıklarını temizle
        response_text = self._clean_tool_artifacts(response_text)

        result = {
            "model": "relay-v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "response": response_text,
            "done": True,
        }
        self._json_response(200, result)

    def _json_response(self, code: int, data: dict):
        """JSON yanıt gönder."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _clean_tool_artifacts(text: str) -> str:
        """Yanıttan tool call artıklarını temizle."""
        # Yapısal bloklar
        text = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', text, flags=re.DOTALL).strip()
        text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL).strip()
        text = re.sub(r'<function_calls?>.*?</function_calls?>', '', text, flags=re.DOTALL).strip()
        # Code block içinde tool call JSON
        text = re.sub(r'```[a-z]*\s*\n?\s*\{\s*"name"\s*:.*?\}\s*\n?\s*```', '', text, flags=re.DOTALL).strip()
        # Düz JSON tool call
        text = re.sub(r'(?m)^\s*\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{.*?\}\s*\}\s*$', '', text, flags=re.DOTALL).strip()
        # Fonksiyon çağrısı formatları
        text = re.sub(r'(?m)^\s*(?:run_terminal_command|run_in_terminal|execute_command|read_file|list_dir|grep_search|analyze_file|write_file|replace_in_file|file_search|get_errors|multi_grep)\s*\(.*?\)\s*$', '', text, flags=re.DOTALL).strip()
        # TOOL_NAME formatı
        text = re.sub(r'TOOL_NAME:\s*\S+(?:\s+BEGIN_ARG:\s*\S+\s+.*?\s*END_ARG)*', '', text, flags=re.DOTALL).strip()
        # Gemini UI artıkları
        text = re.sub(r'(?m)^\s*Kod snippet[\'\u2018\u2019ı]?\s*$', '', text).strip()
        text = re.sub(r'(?m)^\s*Code snippet\s*$', '', text).strip()
        text = re.sub(r'(?m)^\s*(?:Kopyala|Copy)(?:\s*$)', '', text).strip()
        # Araç sonuç etiketleri (Gemini bazen bunları tekrar eder)
        text = re.sub(r'\[(?:Araç Sonucu|Tool Result)\s*[—-]\s*\w+\]:\s*', '', text).strip()
        text = re.sub(r'\[(?:System Instruction|Previous AI Response|Kullanıcı Sorusu)\]:?\s*', '', text).strip()
        # Ardışık boş satırları düzelt
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    def _cors_headers(self):
        """CORS başlıkları."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _filter_messages(self, messages: list) -> list:
        """Continue'dan gelen mesaj listesini filtrele.
        Gemini her istekte yeni chat açtığı için prompt çok uzun olmamalı,
        ama konuşma bağlamını korumak için yeterli geçmiş de lazım."""
        if len(messages) <= 10:
            return messages  # Kısa geçmiş, olduğu gibi gönder

        # System mesajları her zaman koru
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Son 8 non-system mesajı tam koru (bağlam zinciri)
        recent_msgs = non_system[-8:] if len(non_system) > 8 else non_system

        # Eski mesajları özet olarak dahil et (bağlam kaybını önle)
        old_msgs = non_system[:-8] if len(non_system) > 8 else []
        summary_parts = []
        for msg in old_msgs:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))
            if role == "user" and content.strip():
                # Kullanıcı sorularını kısa tut
                summary_parts.append({"role": "user", "content": content[:200]})
            elif role == "assistant" and content.strip():
                # Asistan cevaplarını özetle (ilk 300 chr)
                summary_parts.append({"role": "assistant", "content": content[:300] + ("..." if len(content) > 300 else "")})

        result = system_msgs + summary_parts + recent_msgs
        if len(result) < len(messages):
            print(f"  🔍 Mesaj filtresi: {len(messages)} → {len(result)} mesaj ({len(summary_parts)} özet + {len(recent_msgs)} son)")
        return result

    def _build_tool_prompt(self, tools):
        """Tool tanımlarını Gemini için metin prompt'una çevir."""
        if not tools:
            return ""

        lines = [
            "KULLANILABİLİR ARAÇLAR:",
        ]

        for tool in tools:
            if tool.get("type") != "function":
                continue
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            params = func.get("parameters", {})

            lines.append(f"\n- {name}: {desc[:150]}")

            properties = params.get("properties", {})
            required = params.get("required", [])
            if properties:
                param_strs = []
                for pname, pinfo in properties.items():
                    req = "*" if pname in required else ""
                    param_strs.append(f"{pname}{req}")
                lines.append(f"  Params: {', '.join(param_strs)}")

        return "\n".join(lines)

    def _parse_tool_calls(self, response_text):
        """Gemini cevabından tool call bloklarını parse et.
        Desteklenen formatlar:
        1. [TOOL_CALL]{"name":...}[/TOOL_CALL]
        2. <tool_call>{"name":...}</tool_call>
        3. ```json {"name":...,"arguments":...} ```
        4. Düz JSON satırı: {"name": "read_file", "arguments": ...}
        """
        tool_calls = []

        # Pattern 1: [TOOL_CALL]...[/TOOL_CALL] (birincil format)
        pattern1 = r'\[TOOL_CALL\]\s*(.*?)\s*\[/TOOL_CALL\]'
        matches = re.findall(pattern1, response_text, re.DOTALL)

        # Pattern 2: <tool_call>...</tool_call> (yedek)
        if not matches:
            pattern2 = r'<tool_call>\s*(.*?)\s*</tool_call>'
            matches = re.findall(pattern2, response_text, re.DOTALL)

        # Pattern 2.5: <function_call>...</function_call> (Gemini alternatif)
        if not matches:
            pattern2b = r'<function_calls?>\s*(.*?)\s*</function_calls?>'
            matches = re.findall(pattern2b, response_text, re.DOTALL)

        # Pattern 3: ```json ... ``` ile sarılı (Gemini genelde bunu kullanır)
        if not matches:
            pattern3 = r'```(?:json|tool_call)?\s*\n?\s*(\{[^`]*?"name"\s*:[^`]*?\})\s*\n?\s*```'
            matches = re.findall(pattern3, response_text, re.DOTALL)

        # Pattern 4.5: TOOL_NAME: ... BEGIN_ARG: ... END_ARG formatı
        # Gemini bazen bu formatı kullanıyor
        if not matches:
            pattern_tn = r'TOOL_NAME:\s*(\S+)(.*)'
            tn_match = re.search(pattern_tn, response_text, re.DOTALL)
            if tn_match:
                tn_name = tn_match.group(1).strip()
                tn_args_text = tn_match.group(2)
                # BEGIN_ARG: key value END_ARG parçalarını çıkar
                arg_pattern = r'BEGIN_ARG:\s*(\S+)\s+(.*?)\s*END_ARG'
                arg_matches = re.findall(arg_pattern, tn_args_text, re.DOTALL)
                tn_args = {}
                # Araç adı eşleştirme (ls→list_dir, cat→read_file vb.)
                tn_alias_map = {
                    'ls': 'list_dir', 'dir': 'list_dir', 'list': 'list_dir',
                    'cat': 'read_file', 'read': 'read_file', 'head': 'read_file',
                    'grep': 'grep_search', 'search': 'grep_search', 'find': 'file_search',
                    'exec': 'run_command', 'run': 'run_command', 'sh': 'run_command',
                    'write': 'write_file', 'edit': 'replace_in_file',
                    'analyze': 'analyze_file', 'errors': 'get_errors',
                }
                resolved_name = tn_alias_map.get(tn_name, tn_name)
                # Argüman adı eşleştirme
                arg_alias_map = {
                    'dirPath': 'path', 'directory': 'path', 'dir': 'path',
                    'file': 'filePath', 'fileName': 'filePath',
                    'recursive': 'recursive',
                }
                for key, val in arg_matches:
                    mapped_key = arg_alias_map.get(key.strip(), key.strip())
                    # Boolean/sayı dönüşümü
                    val = val.strip()
                    if val.lower() == 'true': val = True
                    elif val.lower() == 'false': val = False
                    elif val.isdigit(): val = int(val)
                    tn_args[mapped_key] = val
                matches = [json.dumps({"name": resolved_name, "arguments": tn_args})]
                print(f"  🔧 TOOL_NAME format algılandı: {tn_name} → {resolved_name}({tn_args})")

        # Pattern 4: Düz JSON objesi (doğrudan {"name": "...", "arguments": {...}})
        # Hem Relay araç adlarını hem yaygın alias'ları tanı
        if not matches:
            all_tool_names = '|'.join([
                'read_file', 'list_dir', 'grep_search', 'file_search',
                'run_command', 'write_file', 'replace_in_file',
                'analyze_file', 'get_errors', 'multi_grep',
                # Continue/Copilot alias'ları
                'run_terminal_command', 'run_in_terminal', 'execute_command',
                'terminal_command', 'read_file_content', 'list_directory',
                'search_files', 'search_text', 'create_file', 'edit_file',
                'replace_string_in_file',
            ])
            pattern4 = rf'(\{{"name"\s*:\s*"(?:{all_tool_names})"[^}}]*"arguments"\s*:\s*\{{[^}}]*\}}\s*\}})'
            matches = re.findall(pattern4, response_text, re.DOTALL)

        for match in matches:
            try:
                raw = match.strip()
                # Windows path fix: C:\Users gibi yollar JSON'da geçersiz escape oluşturur
                # \U, \D, \R vb. geçersiz — sadece geçerli JSON escape'leri koru
                raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
                tc_data = json.loads(raw)
                if "name" not in tc_data:
                    continue
                arguments = tc_data.get("arguments", {})
                if isinstance(arguments, dict):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                elif not isinstance(arguments, str):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tc_data["name"],
                        "arguments": arguments
                    }
                })
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ⚠️ Tool call parse hatası: {e}, metin: {match[:100]}")
                continue

        if tool_calls:
            print(f"  🔧 Parsed {len(tool_calls)} tool call(s)")
        else:
            # Debug: response'ta tool ipuçları var mı?
            lower = response_text.lower()
            tool_hints = ['read_file', 'list_dir', 'grep_search', 'file_search', 'tool_call', 'arguments']
            found_hints = [h for h in tool_hints if h in lower]
            if found_hints:
                print(f"  ⚠️ Tool call parse edilemedi ama ipuçları var: {found_hints}")
                print(f"  ⚠️ Raw response: {response_text[:300]}")

        return tool_calls if tool_calls else None


# ══════════════════════════════════════════════════════════════════
# ANA BAŞLATICI
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Relay Ver 1.0 Proxy - VS Code Continue için Sınırsız AI"
    )
    parser.add_argument("--port", type=int, default=5001, help="Sunucu portu (varsayılan: 5001)")
    parser.add_argument("--visible", action="store_true", help="Tarayıcıyı göster (debug için)")
    parser.add_argument("--no-update", action="store_true", help="Güncelleme kontrolünü atla")
    args = parser.parse_args()

    # ═══ OTOMATİK GÜNCELLEME ═══
    if not args.no_update:
        try:
            from relay_updater import check_and_update, notify_owner
            update_result = check_and_update()
            if update_result.get("updated") and "Relay_proxy.py" in str(update_result.get("files", [])):
                print("  🔄 Proxy güncellendi, yeniden başlatılıyor...")
                notify_owner("Güncelleme uygulandı")
                os.execv(sys.executable, [sys.executable] + sys.argv + ["--no-update"])
            # İlk çalıştırmada bildirim
            notify_owner("Relay başlatıldı")
        except ImportError:
            pass  # updater yoksa sessizce devam
        except Exception as e:
            print(f"  ⚠️  Güncelleme kontrolü başarısız: {e}")

    global gemini_bridge

    # Port çakışması kontrolü - eski proxy'yi otomatik temizle
    import socket
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_busy = False
    try:
        test_sock.bind(("127.0.0.1", args.port))
    except OSError:
        port_busy = True
    finally:
        test_sock.close()

    if port_busy:
        print(f"  ⚠️  Port {args.port} zaten kullanılıyor, eski süreç temizleniyor...")
        my_pid = os.getpid()
        my_ppid = os.getppid()
        safe_pids = {my_pid, my_ppid}  # Kendimizi ve parent'ımızı koru
        try:
            # Yöntem 1: Port'u tutan süreci bul ve öldür
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f"Get-NetTCPConnection -LocalPort {args.port} -ErrorAction SilentlyContinue | "
                 f"Select-Object -ExpandProperty OwningProcess -Unique | "
                 f"ForEach-Object {{ $p = Get-Process -Id $_ -ErrorAction SilentlyContinue; "
                 f"if ($p) {{ '{{}},{{}}' -f $p.Id, $p.ProcessName }} }}"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if ',' not in line:
                    continue
                pid_str, proc_name = line.split(',', 1)
                pid_str = pid_str.strip()
                proc_name = proc_name.strip().lower()
                if pid_str.isdigit() and int(pid_str) > 0 and int(pid_str) not in safe_pids:
                    subprocess.run(['taskkill', '/f', '/pid', pid_str], capture_output=True, timeout=5)
                    print(f"  🧹 Port {args.port} süreci sonlandırıldı: {proc_name} (PID {pid_str})")
        except Exception as e:
            print(f"  ⚠️  Port temizleme hatası: {e}")

        try:
            # Yöntem 2: gemini_proxy.py çalıştıran eski Python süreçlerini de öldür
            result2 = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                 "Where-Object { $_.CommandLine -like '*gemini_proxy*' } | "
                 "Select-Object -ExpandProperty ProcessId"],
                capture_output=True, text=True, timeout=5
            )
            for line in result2.stdout.strip().split('\n'):
                pid = line.strip()
                if pid.isdigit() and int(pid) not in safe_pids:
                    subprocess.run(['taskkill', '/f', '/pid', pid], capture_output=True, timeout=5)
                    print(f"  🧹 Eski gemini_proxy süreci sonlandırıldı (PID {pid})")
        except Exception:
            pass

        # Port serbest kalana kadar bekle (max 5sn)
        for _ in range(10):
            time.sleep(0.5)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", args.port))
                s.close()
                print(f"  ✅ Port {args.port} serbest kaldı")
                break
            except OSError:
                continue
        else:
            print(f"  ⚠️  Port {args.port} hâlâ meşgul, yine de devam ediliyor...")

    gemini_bridge = GeminiBridge(headless=not args.visible)

    # Temiz kapatma
    def cleanup(sig, frame):
        print("\n\n🛑 Kapatılıyor...")
        gemini_bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # 1. Gemini tarayıcısını başlat (max 3 deneme)
    started = False
    for attempt in range(3):
        if gemini_bridge.start():
            started = True
            break
        if attempt < 2:
            print(f"\n  🔄 Deneme {attempt + 2}/3 — profil cache temizlenip tekrar deneniyor...")
            # Chrome cache temizle (profil korupsiyon fix)
            import shutil
            for cache_dir in ["Cache", "Code Cache", "GPUCache", "DawnCache", "ShaderCache"]:
                cache_path = os.path.join(GEMINI_PROFILE, "Default", cache_dir)
                if os.path.exists(cache_path):
                    try:
                        shutil.rmtree(cache_path, ignore_errors=True)
                    except Exception:
                        pass
            time.sleep(2)

    if not started:
        print("\n❌ Gemini başlatılamadı!")
        input("Kapatmak için Enter'a basın...")
        sys.exit(1)

    # 2. HTTP sunucuyu başlat (SO_REUSEADDR ile port hemen tekrar kullanılabilir)
    class ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True
    server = ReusableHTTPServer(("127.0.0.1", args.port), OpenAIHandler)
    print(f"\n{'═'*60}")
    print(f"  🚀 RELAY VER 1.0 PROXY HAZIR!")
    print(f"  📡 http://127.0.0.1:{args.port}")
    print(f"  🔗 OpenAI Uyumlu: http://127.0.0.1:{args.port}/v1/chat/completions")
    print(f"  🔗 Ollama Uyumlu: http://127.0.0.1:{args.port}/api/chat")
    print(f"{'═'*60}")
    print(f"\n  Continue VS Code ayarları:")
    print(f'  {{')
    print(f'    "models": [{{')
    print(f'      "title": "Relay Ver 1.0",')
    print(f'      "provider": "openai",')
    print(f'      "model": "relay-v1",')
    print(f'      "apiBase": "http://127.0.0.1:{args.port}/v1",')
    print(f'      "apiKey": "not-needed"')
    print(f'    }}]')
    print(f'  }}')
    print(f"\n  Ctrl+C ile kapatabilirsiniz.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        gemini_bridge.stop()
        server.server_close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        input("\nKapatmak için Enter'a basın...")
        sys.exit(1)
