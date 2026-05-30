import requests
import re
import time
from typing import List, Dict
from bs4 import BeautifulSoup

from logger import setup_logger

logger = setup_logger("KapScraper")

class KapScraper:
    """KAP'ın YENİ arayüzünden günlük bildirimleri çeken web scraping sınıfı."""
    
    def __init__(self):
        # YENİ KAP URL'si
        self.sorgu_url = "https://www.kap.org.tr/tr/bildirim-sorgu-sonuc?srcbar=Y&cmp=Y&cat=6&slf=ODA"
        self.detail_url_template = "https://www.kap.org.tr/tr/Bildirim/{id}"
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        logger.info("YENİ KapScraper modülü başlatıldı.")

    def _bildirim_detayi_al(self, bildirim_id: str) -> str:
        """Sadece bildirimin ID'sini kullanarak arka planda detay sayfasına girer ve asıl metni çeker."""
        url = self.detail_url_template.format(id=bildirim_id)
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Detay alınamadı. HTTP {response.status_code} - ID: {bildirim_id}")
                return ""

            soup = BeautifulSoup(response.text, "html.parser")

            # Senin belirttiğin 'expanded-container' alanını dinamik olarak buluyoruz
            # Bu sayede tablo tr[19] yerine tr[18] olsa bile kod asla patlamaz!
            container = soup.find(id="expanded-container")
            if container:
                # İçindeki tüm metinleri temiz bir şekilde al
                metin = container.get_text(separator="\n", strip=True)
                # Fazladan boşlukları temizle
                return re.sub(r'\n+', '\n', metin)

            # Eğer expanded-container yoksa yedek yöntem (Eski formatlı bildirimler için)
            aranacak_basliklar = ["Ek Açıklamalar", "Açıklamalar", "Açıklama"]
            for baslik_adi in aranacak_basliklar:
                baslik = soup.find(["td", "div"], string=re.compile(baslik_adi, re.IGNORECASE))
                if baslik:
                    icerik_kutusu = baslik.find_next(["td", "div"])
                    if icerik_kutusu:
                        metin = icerik_kutusu.get_text(separator="\n", strip=True)
                        return re.sub(r'\n+', '\n', metin)

            return ""
        except Exception as e:
            logger.error(f"Detay çekme hatası (ID: {bildirim_id}): {e}")
            return ""

    def gunluk_verileri_getir(self) -> List[Dict]:
        """Ana tablodan 'Bugün' olanları filtreler ve verilerini toplar."""
        logger.info("Yeni KAP adresinden 'Bugün' tarihli bildirimler taranıyor...")
        rapor_listesi = []

        try:
            resp = self.session.get(self.sorgu_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Ana tabloyu bul
            tbody = soup.find("tbody")
            if not tbody:
                logger.error("Tablo gövdesi (tbody) bulunamadı! Sayfa yapısı değişmiş olabilir.")
                return []

            # notification1, notification2... şeklinde giden tüm satırları yakala
            satirlar = tbody.find_all("tr", id=re.compile(r"notification\d*"))
            logger.info(f"Sayfada {len(satirlar)} bildirim bulundu. Sadece 'Bugün' olanlar ayıklanıyor...")

            for i, satir in enumerate(satirlar, 1):
                tdler = satir.find_all("td")
                
                # Sütunlar eksikse atla
                if len(tdler) < 8:
                    continue

                # 1. TARİH KONTROLÜ (Senin ilettiğin //td[3] sütunu)
                # tdler[2], Python'da 0'dan başladığı için 3. sütuna denk gelir.
                tarih_metni = tdler[2].get_text(strip=True)
                if "Bugün" not in tarih_metni:
                    continue  # Bugün yazmıyorsa bu bildirimi atla!

                # 2. BİLDİRİM ID'SİNİ BULMA (Mucizevi Checkbox yöntemi)
                checkbox = satir.find("input", type="checkbox")
                if not checkbox or not checkbox.get("id"):
                    continue
                bildirim_id = checkbox.get("id")

                # 3. ŞİRKET KODU (Senin ilettiğin //td[4] sütunu - INVEO)
                # sirket_kodu = tdler[3].get_text(strip=True)
                TAKIP_HISSELERI = {"PENTA", "HEKTS", "AAGYO", "GENKM"}
                if sirket_kodu not in TAKIP_HISSELERI:
                    continue
                # 4. BAŞLIK (Senin ilettiğin //td[7] ve //td[8] sütunları birleştiriliyor)
                ana_baslik = tdler[6].get_text(strip=True)
                alt_baslik = tdler[7].get_text(strip=True)
                tam_baslik = f"{ana_baslik} - {alt_baslik}"

                # 5. DETAY METNİ ÇEKME
                icerik = self._bildirim_detayi_al(bildirim_id)
                if not icerik or len(icerik) < 10:
                    icerik = "Özet: " + tam_baslik # Detay boşsa başlığı özet olarak geç

                # Analiz modülünün (analyzer.py) tam beklediği formatta sözlüğe ekle
                rapor_listesi.append({
                    "sirket": sirket_kodu,
                    "baslik": tam_baslik,
                    "icerik": icerik
                })
                
                # KAP sunucularından ban yememek için her detay sayfasında 0.3 sn bekle
                time.sleep(0.3)

            logger.info(f"Veri çekme başarıyla tamamlandı. İşlenen 'Bugün' kayıt sayısı: {len(rapor_listesi)}")
            return rapor_listesi

        except Exception as e:
            logger.error(f"KAP ana sayfa kazıma hatası: {e}")
            return []

# Test etmek için direkt dosyayı çalıştırırsan burası tetiklenir:
if __name__ == "__main__":
    scraper = KapScraper()
    veriler = scraper.gunluk_verileri_getir()
    print(f"\nÇekilen Bildirim Sayısı: {len(veriler)}")
    if veriler:
        print(f"İlk Bildirim Örneği:\n{veriler[0]}")
