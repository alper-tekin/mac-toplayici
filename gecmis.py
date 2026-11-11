"""Geçmiş sezon toplayıcı: eski sezonların fikstürünü ve bitmiş maçların sayfasını bir kez indirir.

Elle başlatılır (workflow `gecmis.yml`), her tur süre bütçesi dolunca durur ve bir sonraki turu başlatır;
iş bitince zincir kendiliğinden durur. Yanıtlar olduğu gibi gzip'lenip veri deposunun ayrı bir dalına yazılır:
  gecmis/leagues/<lig>_<YYYY-YYYY>.json.gz    fikstür (leagues uç noktası)
  gecmis/matches/<maç>.json.gz                maç sayfası (matchDetails)
  gecmis/durum.json                           ilerleme
Çıktıya yalnız sayılar basılır. İstekler arasında 3-4,5 sn beklenir; üst üste 5 hata olursa tur durur.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from pathlib import Path

from toplayici import istek, json_oku, json_yaz, mac_nesneleri

LIGLER = [47, 87, 55, 54, 53, 71, 57, 61, 40, 42, 73, 10216]   # 9 lig + ŞL, AL, KL
SEZONLAR = ['2019/2020', '2020/2021', '2021/2022', '2022/2023']
KL_ILK = '2021/2022'          # Konferans Ligi bu sezon başladı
BEKLE = (3.0, 4.5)
ARDISIK_HATA = 5


# Yeni ligler (2026-11-08): kabul testi için 2019/20–2025/26 tamamlanmış sezonlar. Sezon adları FotMob'un
# allAvailableSeasons listesinden; takvim yılıyla oynayan ligler farklı biçim kullanıyor.
AVRUPA_SEZON = ['2019/2020', '2020/2021', '2021/2022', '2022/2023', '2023/2024', '2024/2025', '2025/2026']
YIL_SEZON = ['2019', '2020', '2021', '2022', '2023', '2024', '2025']
YENI_LIGLER = [
    (48, AVRUPA_SEZON),    # Championship
    (64, AVRUPA_SEZON),    # İskoçya Premiership
    (38, AVRUPA_SEZON),    # Avusturya Bundesliga
    (69, AVRUPA_SEZON),    # İsviçre Super League
    (46, AVRUPA_SEZON),    # Danimarka Superliga
    (135, AVRUPA_SEZON),   # Yunanistan Super League 1
    (268, YIL_SEZON),      # Brezilya Série A
    (130, YIL_SEZON),      # MLS
    (112, ['2019/2020', '2021', '2022', '2023', '2024', '2025 - Apertura', '2025 - Clausura']),   # Arjantin
]
# Güncel sezonun o güne kadar bitmiş maçları (2026-11-12, yeni ligler oyuncu puanı Faz 0): bulut toplayıcı bu
# ligleri 11 Kasım'dan beri topluyor; önceki maçlar bir kez buradan alınır. Bir sezon bir kez işlenir.
GUNCEL = [(lig, '2026/2027') for lig in (48, 64, 38, 69, 46, 135)] + \
         [(268, '2026'), (130, '2026'), (112, '2026 - Apertura'), (112, '2026 - Clausura')]


def isler() -> list[tuple[int, str]]:
    eski = [(l, s) for s in SEZONLAR for l in LIGLER if not (l == 10216 and s < KL_ILK)]
    return eski + [(l, s) for l, sezonlar in YENI_LIGLER for s in sezonlar] + GUNCEL


def dosya_adi(lig: int, sez: str) -> str:
    return f"{lig}_{sez.replace('/', '-').replace(' ', '')}.json.gz"


def yaz_gz(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(path)


def bitmis(m: dict) -> bool:
    st = m.get('status') or {}
    return bool(st.get('finished')) and not st.get('cancelled') and not st.get('awarded')


def calistir(veri: Path, butce_sn: float, fetch=istek, sleep=time.sleep, saat=time.monotonic) -> dict:
    kok = veri / 'gecmis'
    durum = json_oku(kok / 'durum.json', {'lig_tamam': [], 'bekleyen': [], 'tamam': 0, 'vazgec': {}})
    say = dict(istek=0, lig=0, mac=0, hata=0)
    bas = saat()
    ardisik = 0
    ilk = True

    def iste(path, params):
        nonlocal ilk, ardisik
        if not ilk:
            sleep(random.uniform(*BEKLE))
        ilk = False
        say['istek'] += 1
        try:
            d = fetch(path, params)
            ardisik = 0
            return d
        except Exception:
            say['hata'] += 1
            ardisik += 1
            return None

    for lig, sez in isler():
        anahtar = f'{lig}_{sez}'
        if anahtar in durum['lig_tamam']:
            continue
        if saat() - bas > butce_sn or ardisik >= ARDISIK_HATA:
            break
        d = iste('leagues', {'id': lig, 'season': sez})
        if d is None:
            continue
        yaz_gz(kok / 'leagues' / dosya_adi(lig, sez), d)
        mevcut = set(durum['bekleyen'])
        for m in mac_nesneleri(d):
            mid = str(m['id'])
            if bitmis(m) and mid not in mevcut and not (kok / 'matches' / f'{mid}.json.gz').exists():
                durum['bekleyen'].append(mid)
                mevcut.add(mid)
        durum['lig_tamam'].append(anahtar)
        say['lig'] += 1

    kalan = []
    for i, mid in enumerate(durum['bekleyen']):
        if saat() - bas > butce_sn or ardisik >= ARDISIK_HATA:
            kalan.extend(durum['bekleyen'][i:])
            break
        d = iste('matchDetails', {'matchId': mid})
        if d is None:
            n = durum['vazgec'].get(mid, 0) + 1
            durum['vazgec'][mid] = n
            if n < 3:
                kalan.append(mid)
            continue
        yaz_gz(kok / 'matches' / f'{mid}.json.gz', d)
        durum['tamam'] += 1
        say['mac'] += 1
    durum['bekleyen'] = kalan
    kok.mkdir(parents=True, exist_ok=True)
    json_yaz(kok / 'durum.json', durum)
    say['bekleyen'] = len(kalan)
    say['lig_kalan'] = len(isler()) - len(durum['lig_tamam'])
    say['bitti'] = int(say['bekleyen'] == 0 and say['lig_kalan'] == 0)
    say['durdu_hata'] = int(ardisik >= ARDISIK_HATA)
    return say


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--veri', type=Path, required=True)
    p.add_argument('--butce-dk', type=float, default=45)
    p.add_argument('--durum-cikti', type=Path, help='bitti/durdu bilgisinin yazılacağı dosya (workflow için)')
    a = p.parse_args()
    say = calistir(a.veri, a.butce_dk * 60)
    print(' '.join(f'{k}={v}' for k, v in say.items()))
    if a.durum_cikti:
        a.durum_cikti.write_text(f"bitti={say['bitti']}\ndurdu_hata={say['durdu_hata']}\n", encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
