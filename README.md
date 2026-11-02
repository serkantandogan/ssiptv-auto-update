# SS IPTV Güncel Kanal Listesi

Bu repo, yalnızca açık ve yetkili IPTV kaynaklarını kontrol ederek SS IPTV ve VLC ile kullanılabilecek güncel bir M3U listesi üretir.

## Güncel Durum

Her otomatik çalışmada kanal sayısı, kategori dağılımı ve son kontrol zamanı güncellenir:

[Güncel kanal durumu](public/durum.md)

## SS IPTV / VLC bağlantısı

```text
https://raw.githubusercontent.com/serkantandogan/ssiptv-auto-update/main/public/ssiptv.m3u
```

Bu bağlantıyı SS IPTV’ye veya VLC’de `Medya > Ağ Akışı Aç` bölümüne ekleyebilirsin.

## İçerik

- `Favori Listem` kategorisi: Öncelikli kanallar
- Ulusal, Haber, Ekonomi, Belgesel, Çocuk, Spor, Müzik, Kültür, Eğitim ve diğer kategoriler
- Türkiye public kanallarına ek olarak dünya public Haber, Spor, Çocuk, Belgesel, Müzik ve Ekonomi kaynakları
- Yabancı kanallar `Dünya Kanalları` altında kendi alt kategorileriyle listelenir
- Çalışmayan yayın adresleri otomatik olarak listeden çıkarılır
- Resmi sayfadan süreli yayın adresi alınan kanallar her çalışmada yeniden güncellenir
- GitHub Actions listeyi yaklaşık 6 saatte bir yeniler

## Kaynak ve kullanım sınırı

Kaynak olarak açıkça yayınlanmış public kanallar ve resmi canlı yayın sayfaları kullanılır. Ücretli, korumalı veya izinsiz yayın adresleri bilerek listeye eklenmez. `sources.yml` içindeki kaynaklar ve filtreler bu amaçla tutulur.

## Elle güncelleme

GitHub’da `Actions > Update SS IPTV playlist > Run workflow` yoluyla elle çalıştırabilirsin.

## Yerelde çalıştırma

```bash
python -m pip install -r requirements.txt
python scripts/update_playlist.py
```

Üretilen dosyalar:

- `public/ssiptv.m3u`: SS IPTV/VLC playlisti
- `public/durum.md`: Türkçe güncelleme özeti
- `public/validation-report.json`: Kanal bazlı doğrulama raporu

## English

This repository generates an automatically updated, SS IPTV-compatible M3U playlist from public and authorized IPTV sources.

- Turkish channels stay in Turkish categories such as `Ulusal`, `Haber`, `Spor` and `Belgesel`.
- Foreign channels are grouped under `Dünya Kanalları / ...`, for example `Dünya Kanalları / Haber` and `Dünya Kanalları / Spor`.
- `Favori Listem` contains the selected favorite channels.
- Stream URLs are checked automatically and unavailable entries are removed from the generated playlist.
- GitHub Actions refreshes the playlist approximately every 6 hours.

Playlist URL:

```text
https://raw.githubusercontent.com/serkantandogan/ssiptv-auto-update/main/public/ssiptv.m3u
```

The project uses public or authorized sources only. Paid, protected or unauthorized streams are intentionally excluded.

