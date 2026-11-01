# mac-toplayici

Kişisel, kâr amacı olmayan bir futbol analizi hobi projesi için küçük bir veri toplayıcı.
Ticari kullanım, reklam ya da ücretli hizmet yoktur.

Her 5 dakikada bir FotMob'un herkese açık maç sayfasındaki verileri ister:
maç öncesi muhtemel kadro (saatte bir), açıklanan ilk 11 (maçtan ~50 dk önce)
ve maç sonu istatistikleri (maçtan 3 saat sonra, 15 dk arayla, tamamlanana kadar).
İstekler arasında 2–4 saniye beklenir ve bir turda en çok 80 istek yapılır.

Ayrıca elle çalıştırılan `Oranlar` işi football-data.co.uk'nin herkese açık sezon CSV'lerini
(9 lig, 8 sezon; 3 saniye arayla) bir kez indirir.

Elle başlatılan `Gecmis` işi, 2019/20–2022/23 sezonlarının fikstürünü ve bitmiş maçların sayfasını
bir kez ister (istekler arası 3–4,5 sn). Her tur ~45 dakikadır, iş bitince kendiliğinden durur.

Elle başlatılan `Understat` işi, beş büyük ligin 2019/20–2022/23 sezonlarında Understat'ın herkese açık
lig ve maç verisini (şutlar) aynı kurallarla bir kez ister.

Toplanan veri bu depoda tutulmaz; çalışma kayıtlarında yalnız sayılar görünür.

Son aylık çalışma: 2026-11-01
