#!/usr/bin/env python3
"""
Continue Extension Türkçe Yama
==============================
Continue VS Code extension'ının GUI stringlerini Türkçeleştirir.
Sadece kullanıcıya görünen metinleri değiştirir, API state değerlerine dokunmaz.

Kullanım:
    python patch_continue_tr.py          # Yama uygula
    python patch_continue_tr.py --undo   # Yamayı geri al
"""

import os
import sys
import shutil
import re

# Continue extension yolu
EXT_DIR = os.path.join(os.environ["USERPROFILE"], ".vscode", "extensions")
CONTINUE_DIR = None
for d in os.listdir(EXT_DIR):
    if d.startswith("continue.continue-") and os.path.isdir(os.path.join(EXT_DIR, d)):
        CONTINUE_DIR = os.path.join(EXT_DIR, d)
        break

if not CONTINUE_DIR:
    print("❌ Continue extension bulunamadı!")
    sys.exit(1)

GUI_JS = os.path.join(CONTINUE_DIR, "gui", "assets", "index.js")
PKG_JSON = os.path.join(CONTINUE_DIR, "package.json")
BACKUP_JS = GUI_JS + ".backup_original"
BACKUP_PKG = PKG_JSON + ".backup_original"

# ═══════════════════════════════════════════════════════════
# ÇEVRILECEK STRINGLER — index.js
# ═══════════════════════════════════════════════════════════
# Format: (orijinal_metin, türkçe_metin)
# DİKKAT: Sadece UI-visible metinler — state/rol değerleri DEĞİL

GUI_REPLACEMENTS = [
    # ── Ana durum göstergeleri (tool call status labels) ──
    ('return"Performing"', 'return"Çalıştırılıyor"'),
    ('?"Performing":', '?"Çalıştırılıyor":'),
    ('?"Generating":', '?"Yazıyor":'),
    ('?"Pending":', '?"Beklemede":'),
    ('?"Performed":', '?"Tamamlandı":'),
    ('?"Attempted":"Performing"', '?"Denendi":"Çalıştırılıyor"'),
    
    # ── tool call verb prefixes ──
    ('case"generating":return"will"', 'case"generating":return"kullanacak"'),
    ('case"generated":return"wants to"', 'case"generated":return"kullanmak istiyor"'),
    ('case"calling":return"is"', 'case"calling":return"kullanıyor"'),
    ('case"errored":return"tried to"', 'case"errored":return"kullanmayı denedi"'),
    
    # ── Thinking / Düşünme ──
    ('"Redacted Thinking":"Thinking"', '"Gizli Düşünce":"Düşünüyor"'),
    ('"Redacted Thinking":"Thought"', '"Gizli Düşünce":"Düşündü"'),
    
    # ── Editing label ──
    ('"Editing:"', '"Düzenleniyor:"'),
    
    # ── Tool output messages ──
    ('"No tool output"', '"Araç çıktısı yok"'),
    ('"No tool call output"', '"Araç çağrı çıktısı yok"'),
    ('"The user cancelled this tool call."', '"Kullanıcı bu araç çağrısını iptal etti."'),
    ('"There was an error calling the tool."', '"Araç çağrılırken hata oluştu."'),
    
    # ── Accept / Reject / Apply buttons ──
    ('children:"Accept"', 'children:"Kabul Et"'),
    ('children:"Reject"', 'children:"Reddet"'),
    ('children:"Apply"', 'children:"Uygula"'),
    
    # ── Indexing ──
    ('title:"Indexing"', 'title:"Dizin Oluşturuluyor"'),
    ('label:"Indexing"', 'label:"Dizin Oluşturuluyor"'),
    
    # ── Input placeholder / chat input ──
    # JVe fonksiyonu: t||(e===0?"Ask anything...":"Ask a follow-up")
    ('"Ask anything, \'@\' to add context"', '"Ne oluşturulacağını açıkla"'),
    ('"Ask a follow-up"', '"Devam sorusu sor"'),
    ('placeholder:"Search past sessions"', 'placeholder:"Geçmiş oturumları ara"'),
    
    # ── Session / Chat ──
    ('const sx="New Session"', 'const sx="Yeni Oturum"'),
    ('children:"Start a new session"', 'children:"Yeni oturum başlat"'),
    ('children:"Last Session"', 'children:"Son Oturum"'),
    ('children:"Clear chats"', 'children:"Sohbetleri temizle"'),
    ('children:"Save Chat as Markdown"', 'children:"Sohbeti Markdown olarak kaydet"'),
    ('children:"Compact conversation"', 'children:"Sohbeti sıkıştır"'),
    ('children:"Previous Conversation Compacted"', 'children:"Önceki Sohbet Sıkıştırıldı"'),
    ('children:"Generating conversation summary"', 'children:"Sohbet özeti oluşturuluyor"'),
    ('children:"Conversation Summary"', 'children:"Sohbet Özeti"'),
    
    # ── Navigation tabs ──
    ('children:"Chat"', 'children:"Sohbet"'),
    ('children:"Agent"', 'children:"Ajan"'),
    
    # ── Retry / Edit ──
    ('"Retry"', '"Tekrar Dene"'),
    
    # ── Copy / Cancel / Close ──
    ('children:"Copy"', 'children:"Kopyala"'),
    ('children:"Copy output"', 'children:"Çıktıyı kopyala"'),
    ('children:"Cancel"', 'children:"İptal"'),
    ('children:"Close"', 'children:"Kapat"'),
    ('children:"Run"', 'children:"Çalıştır"'),
    
    # ── Log in/out ──
    ('children:"Log out"', 'children:"Çıkış yap"'),
    ('children:"Log in"', 'children:"Giriş yap"'),
    ('children:"Manage Account"', 'children:"Hesabı Yönet"'),
    
    # ── View Logs ──
    ('children:"View Logs"', 'children:"Günlükleri Gör"'),
    ('children:"Reload"', 'children:"Yeniden Yükle"'),
    
    # ── Settings / Model cards ──
    ('children:"Models"', 'children:"Modeller"'),
    ('children:"No models configured"', 'children:"Yapılandırılmış model yok"'),
    ('children:"Add Chat model"', 'children:"Sohbet modeli ekle"'),
    ('children:"No results"', 'children:"Sonuç yok"'),
    ('children:"Loading config"', 'children:"Yapılandırma yükleniyor"'),
    
    # ── Resources / Tools / Keyboard ──
    ('children:"Resources"', 'children:"Kaynaklar"'),
    ('children:"Tools"', 'children:"Araçlar"'),
    ('children:"Keyboard Shortcuts"', 'children:"Klavye Kısayolları"'),
    
    # ── Error messages ──
    ('children:"Error handling model response"', 'children:"Model yanıtı işlenirken hata"'),
    ('children:"Error loading"', 'children:"Yükleme hatası"'),
    ('children:"Check API key"', 'children:"API anahtarını kontrol et"'),
    ('children:"Resubmit last message"', 'children:"Son mesajı tekrar gönder"'),
    ('children:"View config"', 'children:"Yapılandırmayı gör"'),
    ('children:"Try again"', 'children:"Tekrar dene"'),
    
    # ── Help / Settings ──
    ('children:"Help"', 'children:"Yardım"'),
    ('children:"Open config"', 'children:"Yapılandırmayı aç"'),
    ('children:"Config"', 'children:"Yapılandırma"'),
    ('children:"Discussions"', 'children:"Tartışmalar"'),
    ('children:"Hide"', 'children:"Gizle"'),
    ('children:"Restart"', 'children:"Yeniden Başlat"'),
    ('children:"Submit"', 'children:"Gönder"'),
    ('children:"Not now"', 'children:"Şimdi değil"'),
    ('children:"Back"', 'children:"Geri"'),
    ('children:"Continue"', 'children:"Devam"'),
    ('children:"Generate"', 'children:"Oluştur"'),
    ('children:"Generate Rule"', 'children:"Kural Oluştur"'),
    ('children:"Create"', 'children:"Oluştur"'),
    ('children:"Add"', 'children:"Ekle"'),
    ('children:"Learn more"', 'children:"Daha fazla bilgi"'),
    
    # ── Terminal ──
    ('children:"Terminal"', 'children:"Terminal"'),
    ('children:"Move to background"', 'children:"Arka plana taşı"'),
    
    # ── Tool permission ──
    ('children:"Automatic"', 'children:"Otomatik"'),
    ('children:"Ask First"', 'children:"Önce Sor"'),
    ('children:"Excluded"', 'children:"Hariç Tutuldu"'),
    
    # ── Docs ──
    ('children:"Add documentation"', 'children:"Dokümantasyon ekle"'),
    ('children:"Add docs"', 'children:"Doküman ekle"'),
    
    # ── Delete summary tooltip ──
    ('"Delete summary"', '"Özeti sil"'),
    
    # ── Indexing messages ──
    ('children:"Indexing is disabled"', 'children:"Dizinleme devre dışı"'),
    ('children:"Indexing has been deprecated"', 'children:"Dizinleme kaldırıldı"'),
    
    # ── Background ──
    ('children:"Background Tasks"', 'children:"Arka Plan Görevleri"'),
    ('children:"Background Agents"', 'children:"Arka Plan Ajanları"'),
    
    # ── Rule editor ──
    ('children:"Your rule"', 'children:"Kuralınız"'),
    ('children:"Rule Name"', 'children:"Kural Adı"'),
    ('children:"Rule Type"', 'children:"Kural Türü"'),
    ('children:"Rule Content"', 'children:"Kural İçeriği"'),
    ('children:"Rule name"', 'children:"Kural adı"'),
    ('children:"Always"', 'children:"Her Zaman"'),
    ('children:"Auto Attached"', 'children:"Otomatik Eklenen"'),
    ('children:"Agent Requested"', 'children:"Ajan Talep Etti"'),
    ('children:"Manual"', 'children:"Manuel"'),
    ('children:"Description"', 'children:"Açıklama"'),
    ('children:"File pattern matches"', 'children:"Dosya deseni eşleşmeleri"'),
    ('children:"Applies to files"', 'children:"Dosyalara uygulanır"'),
    
    # ── GJ Applying text ──
    ('text:"Applying"', 'text:"Uygulanıyor"'),
    
    # ── Tooltips (Us component) ──
    ('text:"Delete"', 'text:"Sil"'),
    ('text:"Previous Match"', 'text:"Önceki Eşleşme"'),
    ('text:"Next Match"', 'text:"Sonraki Eşleşme"'),
    ('text:"Helpful"', 'text:"Faydalı"'),
    ('text:"Unhelpful"', 'text:"Faydalı Değil"'),
    ('text:"Generate rule"', 'text:"Kural oluştur"'),
    ('text:"Continue generation"', 'text:"Oluşturmaya devam et"'),
    ('text:"Expand"', 'text:"Genişlet"'),
    ('text:"View"', 'text:"Görüntüle"'),
    ('text:"Edit"', 'text:"Düzenle"'),
    ('text:"Open in browser"', 'text:"Tarayıcıda aç"'),
    ('text:"Save Chat as Markdown"', 'text:"Sohbeti Markdown olarak kaydet"'),
    
    # ── Esc / Edit mode ──
    ('" to exit Edit"', '" ile Düzenlemeden çık"'),
    ('"Please open a file to use Edit mode"', '"Düzenleme modu için bir dosya açın"'),
    
    # ── Thinking animated label ──
    ('children:`Thinking.${".".repeat(e)}`', 'children:`Düşünüyor.${".".repeat(e)}`'),
    
    # ── No X messages ──
    ('children:"No config found"', 'children:"Yapılandırma bulunamadı"'),
    ('children:"No changes to display"', 'children:"Görüntülenecek değişiklik yok"'),
    ('children:"No article chunks"', 'children:"Makale parçası yok"'),
    
    # ── Action items ──
    ('children:"Delete"', 'children:"Sil"'),
    ('children:"Edit"', 'children:"Düzenle"'),
    ('children:"Refresh agent secrets"', 'children:"Ajan gizli anahtarlarını yenile"'),
    ('children:"Organizations"', 'children:"Organizasyonlar"'),
    ('children:"Configs"', 'children:"Yapılandırmalar"'),
    ('children:"View"', 'children:"Görüntüle"'),
    
    # ── Remaining Save ──
    ('children:"Save"', 'children:"Kaydet"'),
    
    # ── Search placeholder ──
    ('placeholder:"Search..."', 'placeholder:"Ara..."'),
    ('placeholder:"Title"', 'placeholder:"Başlık"'),
    ('placeholder:"Start URL"', 'placeholder:"Başlangıç URL"'),
    ('placeholder:"Name"', 'placeholder:"Ad"'),
    ('placeholder:"Email"', 'placeholder:"E-posta"'),
    ('placeholder:"Description of the task this rule is helpful for..."', 'placeholder:"Bu kuralın faydalı olduğu görevin açıklaması..."'),
    ('placeholder:"Your rule content..."', 'placeholder:"Kural içeriğiniz..."'),
    ('placeholder:"Describe your rule..."', 'placeholder:"Kuralınızı açıklayın..."'),
    
    # ── Settings page titles ──
    ('title:"User Settings"', 'title:"Kullanıcı Ayarları"'),
    ('title:"Chat"', 'title:"Sohbet"'),
    ('title:"Show Session Tabs"', 'title:"Oturum Sekmelerini Göster"'),
    ('title:"Wrap Codeblocks"', 'title:"Kod Bloklarını Kaydır"'),
    ('title:"Show Chat Scrollbar"', 'title:"Sohbet Kaydırma Çubuğunu Göster"'),
    ('title:"Text-to-Speech Output"', 'title:"Metin-Konuşma Çıktısı"'),
    ('title:"Enable Session Titles"', 'title:"Oturum Başlıklarını Etkinleştir"'),
    ('title:"Format Markdown"', 'title:"Markdown Biçimlendir"'),
    ('title:"Telemetry"', 'title:"Telemetri"'),
    ('title:"Allow Anonymous Telemetry"', 'title:"Anonim Telemetriye İzin Ver"'),
    ('title:"Appearance"', 'title:"Görünüm"'),
    ('title:"Font Size"', 'title:"Yazı Boyutu"'),
    ('title:"Autocomplete"', 'title:"Otomatik Tamamlama"'),
    ('title:"Multiline Autocompletions"', 'title:"Çok Satırlı Otomatik Tamamlama"'),
    ('title:"Autocomplete Timeout (ms)"', 'title:"Otomatik Tamamlama Zaman Aşımı (ms)"'),
    ('title:"Autocomplete Debounce (ms)"', 'title:"Otomatik Tamamlama Gecikme (ms)"'),
    ('title:"Disable autocomplete in files"', 'title:"Dosyalarda otomatik tamamlamayı kapat"'),
    ('title:"Experimental"', 'title:"Deneysel"'),
    ('title:"Show Experimental Settings"', 'title:"Deneysel Ayarları Göster"'),
    ('title:"Add Current File by Default"', 'title:"Varsayılan Olarak Mevcut Dosyayı Ekle"'),
    ('title:"Enable experimental tools"', 'title:"Deneysel araçları etkinleştir"'),
    ('title:"Only use system message tools"', 'title:"Sadece sistem mesajı araçlarını kullan"'),
    ('title:"Stream after tool rejection"', 'title:"Araç reddi sonrası akış"'),
    ('title:"Models"', 'title:"Modeller"'),
    ('title:"Additional model roles"', 'title:"Ek model rolleri"'),
    ('title:"Apply, Embed, Rerank"', 'title:"Uygula, Gömme, Yeniden Sırala"'),
    ('title:"Organizations"', 'title:"Organizasyonlar"'),
    ('title:"Delete Rule"', 'title:"Kuralı Sil"'),
    ('title:"Prompts"', 'title:"Komut İstemleri"'),
    ('title:"Rules"', 'title:"Kurallar"'),
    ('title:"Resources"', 'title:"Kaynaklar"'),
    ('title:"Tools"', 'title:"Araçlar"'),
    ('title:"MCP Servers"', 'title:"MCP Sunucuları"'),
    ('title:"Help Center"', 'title:"Yardım Merkezi"'),
    ('title:"Documentation"', 'title:"Dokümantasyon"'),
    ('title:"Have an issue?"', 'title:"Bir sorun mu var?"'),
    ('title:"Join the community!"', 'title:"Topluluğa katılın!"'),
    ('title:"Token usage"', 'title:"Token kullanımı"'),
    ('title:"View current session history"', 'title:"Mevcut oturum geçmişini görüntüle"'),
    ('title:"Quickstart"', 'title:"Hızlı Başlangıç"'),
    ('title:"Rebuild codebase index"', 'title:"Kod tabanı dizinini yeniden oluştur"'),
    ('title:"View detailed docs information"', 'title:"Detaylı doküman bilgisini görüntüle"'),
    ('title:"Enable indexing"', 'title:"Dizinlemeyi etkinleştir"'),
    ('title:"Add Docs"', 'title:"Doküman Ekle"'),
    ('title:"New .prompt file"', 'title:"Yeni .prompt dosyası"'),
    ('title:"Add new rule"', 'title:"Yeni kural ekle"'),
    ('title:"View error output"', 'title:"Hata çıktısını görüntüle"'),
    ('title:"Always Applied"', 'title:"Her Zaman Uygulanır"'),
    ('title:"Auto attached"', 'title:"Otomatik eklenen"'),
    ('title:"Agent Requested"', 'title:"Ajan Talep Etti"'),
    ('title:"Manual"', 'title:"Manuel"'),
    ('title:"Configs"', 'title:"Yapılandırmalar"'),
    ('title:"Loading..."', 'title:"Yükleniyor..."'),
    ('title:"Loading models..."', 'title:"Modeller yükleniyor..."'),
    
    # ── Nav labels ──
    ('label:"Back"', 'label:"Geri"'),
    ('label:"Models"', 'label:"Modeller"'),
    ('label:"Rules"', 'label:"Kurallar"'),
    ('label:"Tools"', 'label:"Araçlar"'),
    ('label:"Current workspace"', 'label:"Mevcut çalışma alanı"'),
    ('label:"Global"', 'label:"Genel"'),
    ('label:"Open in new tab"', 'label:"Yeni sekmede aç"'),
    ('label:"Starter credits usage"', 'label:"Başlangıç kredisi kullanımı"'),
    
    # ── Misc visible ──
    ('children:"Starter credits"', 'children:"Başlangıç kredileri"'),
    ('children:"Setup API Keys"', 'children:"API Anahtarlarını Ayarla"'),
    ('children:"Purchase Credits"', 'children:"Kredi Satın Al"'),
    ('children:"Help us improve Continue"', 'children:"Continue\'u geliştirmemize yardımcı olun"'),
    ('children:"Plan"', 'children:"Plan"'),
    ('children:"Background"', 'children:"Arka Plan"'),
    ('children:"Remote"', 'children:"Uzak"'),
    ('children:"Docs index"', 'children:"Doküman dizini"'),
    ('children:"Continue Anyway"', 'children:"Yine de Devam Et"'),
    ('children:"Limited Functionality"', 'children:"Sınırlı İşlevsellik"'),
    ('children:"Open Dev Tools"', 'children:"Geliştirici Araçlarını Aç"'),
    ('children:"Connect GitHub"', 'children:"GitHub Bağla"'),
    ('children:"Connect GitHub Account"', 'children:"GitHub Hesabını Bağla"'),
    
    # ── Font boyutu küçültme (14 → 12) ──
    ('return Fa("fontSize")??(el()?15:14)', 'return Fa("fontSize")??(el()?13:12)'),
    
    # ── Sohbet input kutusu her zaman altta (boş sohbette de) ──
    ('${f.length>0?"flex-1":""}', '${"flex-1"}'),
    
    # ── Shortcut descriptions ──
    ('description:"Toggle Selected Model"', 'description:"Seçili Modeli Değiştir"'),
    ('description:"Edit highlighted code"', 'description:"Seçili kodu düzenle"'),
    ('description:"Toggle inline edit focus"', 'description:"Satır içi düzenleme odağını aç/kapat"'),
    ('description:"Toggle Autocomplete Enabled"', 'description:"Otomatik tamamlamayı aç/kapat"'),
    ('description:"Toggle Full Screen"', 'description:"Tam ekranı aç/kapat"'),
    ('description:"Toggle Sidebar"', 'description:"Kenar çubuğunu aç/kapat"'),
]

# ═══════════════════════════════════════════════════════════
# ÇEVRILECEK STRINGLER — package.json (komut başlıkları)
# ═══════════════════════════════════════════════════════════

PKG_REPLACEMENTS = [
    # Komut başlıkları
    ('"Apply code from chat"', '"Sohbetten kodu uygula"'),
    ('"Accept Diff"', '"Farkı Kabul Et"'),
    ('"Reject Diff"', '"Farkı Reddet"'),
    ('"Accept Vertical Diff Block"', '"Dikey Fark Bloğunu Kabul Et"'),
    ('"Reject Vertical Diff Block"', '"Dikey Fark Bloğunu Reddet"'),
    ('"Add to Edit"', '"Düzenlemeye Ekle"'),
    ('"Add Highlighted Code to Context and Clear Chat"', '"Seçili Kodu Bağlama Ekle ve Sohbeti Temizle"'),
    ('"Add to Chat"', '"Sohbete Ekle"'),
    ('"Debug Terminal"', '"Terminali Hata Ayıkla"'),
    ('"Exit Edit Mode"', '"Düzenleme Modundan Çık"'),
    ('"Open Settings"', '"Ayarları Aç"'),
    ('"Toggle Autocomplete Enabled"', '"Otomatik Tamamlamayı Aç/Kapat"'),
    ('"New Session"', '"Yeni Oturum"'),
    ('"Share Current Chat Session as Markdown"', '"Mevcut Sohbeti Markdown Olarak Paylaş"'),
    ('"View History"', '"Geçmişi Görüntüle"'),
    ('"View Logs"', '"Günlükleri Görüntüle"'),
    ('"Clear Console"', '"Konsolu Temizle"'),
    ('"Navigate to a path"', '"Bir yola git"'),
    ('"Write Comments for this Code"', '"Bu Kod İçin Yorum Yaz"'),
    ('"Write a Docstring for this Code"', '"Bu Kod İçin Docstring Yaz"'),
    ('"Fix this Code"', '"Bu Kodu Düzelt"'),
    ('"Optimize this Code"', '"Bu Kodu Optimize Et"'),
    ('"Fix Grammar / Spelling"', '"Dilbilgisi / Yazım Düzelt"'),
    ('"Codebase Force Re-Index"', '"Kod Tabanını Yeniden Dizinle"'),
    ('"Rebuild codebase index"', '"Kod tabanı dizinini yeniden oluştur"'),
    ('"Focus Continue Chat"', '"Continue Sohbetine Odaklan"'),
    ('"Generate Rule"', '"Kural Oluştur"'),
    ('"Open in new window"', '"Yeni pencerede aç"'),
    ('"Select Files as Context"', '"Bağlam Olarak Dosya Seç"'),
    ('"Hide Next Edit Suggestion"', '"Sonraki Düzenleme Önerisini Gizle"'),
    ('"Accept Next Edit Suggestion"', '"Sonraki Düzenleme Önerisini Kabul Et"'),
]

def apply_patch():
    """Yamayı uygula."""
    if not os.path.isfile(GUI_JS):
        print(f"❌ {GUI_JS} bulunamadı!")
        return False
    
    # Backup al (sadece ilk seferde)
    if not os.path.isfile(BACKUP_JS):
        shutil.copy2(GUI_JS, BACKUP_JS)
        print(f"  📦 Yedek alındı: {os.path.basename(BACKUP_JS)}")
    if not os.path.isfile(BACKUP_PKG):
        shutil.copy2(PKG_JSON, BACKUP_PKG)
        print(f"  📦 Yedek alındı: {os.path.basename(BACKUP_PKG)}")
    
    # ═══ INDEX.JS YAMALARI ═══
    content = open(GUI_JS, "r", encoding="utf-8").read()
    changes = 0
    
    print("  ── index.js ──")
    for old, new in GUI_REPLACEMENTS:
        count = content.count(old)
        if count > 0:
            content = content.replace(old, new)
            changes += count
            print(f"  ✅ {old[:40]:40s} → {new[:30]}")
        else:
            if new in content:
                pass  # zaten uygulanmış, sessizce geç
            else:
                print(f"  ⚠️  Bulunamadı: {old[:50]}")
    
    if changes > 0:
        open(GUI_JS, "w", encoding="utf-8").write(content)
    
    # ═══ DİNAMİK MODEL ADI YAMASI (GJ fonksiyonu) ═══
    content = open(GUI_JS, "r", encoding="utf-8").read()
    gj_pattern = r'function GJ\(\{text:t="[^"]*",testId:e\}\)\{return'
    gj_match = re.search(gj_pattern, content)
    
    if not gj_match:
        if 'function GJ({text:t,testId:e}){var _m=qe(yc)' in content:
            pass  # zaten uygulanmış
        else:
            print(f"  ⚠️  GJ fonksiyonu bulunamadı")
    else:
        old_gj = gj_match.group(0)
        new_gj = 'function GJ({text:t,testId:e}){var _m=qe(yc);if(!t){t=(_m&&_m.title||"Model")+" Yaz\\u0131yor";}return'
        content = content.replace(old_gj, new_gj, 1)
        open(GUI_JS, "w", encoding="utf-8").write(content)
        changes += 1
        print(f"  ✅ GJ → dinamik model adı")
    
    # ═══ SOHBET LAYOUT FIX (input kutusu her zaman altta) ═══
    content = open(GUI_JS, "r", encoding="utf-8").read()
    layout_old = 'return y.jsxs(y.Fragment,{children:[!!i&&!m&&y.jsx(Ucn,{ref:d}),S,y.jsxs(y3n,{ref:u,className:`overflow-y-scroll pt-[8px] ${O?"thin-scrollbar":"no-scrollbar"} ${"flex-1"}`'
    layout_new = 'return y.jsxs("div",{className:"flex h-full flex-col",children:[!!i&&!m&&y.jsx(Ucn,{ref:d}),S,y.jsxs(y3n,{ref:u,className:`flex-1 overflow-y-scroll pt-[8px] ${O?"thin-scrollbar":"no-scrollbar"}`'
    
    if layout_old in content:
        content = content.replace(layout_old, layout_new, 1)
        open(GUI_JS, "w", encoding="utf-8").write(content)
        changes += 1
        print(f"  ✅ Layout → sohbet input her zaman altta")
    elif 'flex h-full flex-col' in content:
        pass  # zaten uygulanmış
    else:
        print(f"  ⚠️  Layout fix uygulanamadı")
    
    # ═══ PACKAGE.JSON YAMALARI ═══
    pkg_content = open(PKG_JSON, "r", encoding="utf-8").read()
    pkg_changes = 0
    
    print("\n  ── package.json ──")
    for old, new in PKG_REPLACEMENTS:
        count = pkg_content.count(old)
        if count > 0:
            pkg_content = pkg_content.replace(old, new)
            pkg_changes += count
            print(f"  ✅ {old[:40]:40s} → {new[:30]}")
        else:
            if new in pkg_content:
                pass
            else:
                print(f"  ⚠️  Bulunamadı: {old[:50]}")
    
    if pkg_changes > 0:
        open(PKG_JSON, "w", encoding="utf-8").write(pkg_content)
    
    total = changes + pkg_changes
    if total > 0:
        print(f"\n  🎉 Toplam {total} değişiklik ({changes} index.js + {pkg_changes} package.json)")
        print(f"  ⚠️  VS Code'u yeniden başlatın (Ctrl+Shift+P → Reload Window)")
        return True
    else:
        print("\n  ℹ️  Değişiklik yapılmadı (zaten uygulanmış olabilir)")
        return False


def undo_patch():
    """Yamayı geri al.""" 
    restored = False
    if os.path.isfile(BACKUP_JS):
        shutil.copy2(BACKUP_JS, GUI_JS)
        print(f"  ✅ index.js geri yüklendi")
        restored = True
    else:
        print("  ⚠️  index.js yedeği bulunamadı")
    
    if os.path.isfile(BACKUP_PKG):
        shutil.copy2(BACKUP_PKG, PKG_JSON)
        print(f"  ✅ package.json geri yüklendi")
        restored = True
    else:
        print("  ⚠️  package.json yedeği bulunamadı")
    
    if restored:
        print(f"  ⚠️  VS Code'u yeniden başlatın (Ctrl+Shift+P → Reload Window)")
    else:
        print("  ❌ Yedek dosya bulunamadı! Geri alınamıyor.")
    return restored


if __name__ == "__main__":
    print("═" * 50)
    print("  Continue Extension Türkçe Yama")
    print("═" * 50)
    print(f"  Extension: {os.path.basename(CONTINUE_DIR)}")
    print()
    
    if "--undo" in sys.argv:
        print("  🔄 Yama geri alınıyor...\n")
        undo_patch()
    else:
        print("  🇹🇷 Türkçe yama uygulanıyor...\n")
        apply_patch()
