"""Understat toplayıcı: beş büyük ligin eski sezonlarında lig verisi ve maç başına şutlar (xG), bir kez.

Elle başlatılır (workflow `understat.yml`), her tur süre bütçesi dolunca durur ve bir sonraki turu başlatır;
iş bitince zincir kendiliğinden durur. Yanıtlar olduğu gibi gzip'lenip veri deposunun ayrı bir dalına yazılır:
  understat/leagues/<lig>_<yıl>.json.gz     getLeagueData yanıtı (takımlar, oyuncular, maç listesi)
  understat/matches/<maç>.json.gz           getMatchData yanıtı (kadrolar, şutlar)
  understat/durum.json                      ilerleme
Çıktıya yalnız sayılar basılır. İstekler arasında 3-4,5 sn beklenir; üst üste 5 hata olursa tur durur.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import time
from pathlib import Path

from toplayici import json_oku, json_yaz

BASE = 'https://understat.com'
LIGLER = ['EPL', 'La_liga', 'Serie_A', 'Bundesliga', 'Ligue_1']
YILLAR = [2019, 2020, 2021, 2022]          # sezonun başladığı yıl (2019 = 2019/20)
BEKLE = (3.0, 4.5)
ARDISIK_HATA = 5


def istek(path: str, referer: str) -> dict:
    from curl_cffi import requests
    r = requests.get(f'{BASE}/{path}', headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{BASE}/{referer}'},
                     impersonate='chrome', timeout=30, verify=os.environ.get('TOPLAYICI_CA') or True)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}')
    data = r.json()
    if not isinstance(data, dict) or not data:
        raise RuntimeError('boş yanıt')
    return data


def yaz_gz(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(path)


def isler() -> list[tuple[str, int]]:
    return [(l, y) for y in YILLAR for l in LIGLER]


def calistir(veri: Path, butce_sn: float, fetch=istek, sleep=time.sleep, saat=time.monotonic) -> dict:
    kok = veri / 'understat'
    durum = json_oku(kok / 'durum.json', {'lig_tamam': [], 'bekleyen': [], 'tamam': 0, 'vazgec': {}})
    say = dict(istek=0, lig=0, mac=0, hata=0)
    bas = saat()
    ardisik = 0
    ilk = True

    def iste(path, referer):
        nonlocal ilk, ardisik
        if not ilk:
            sleep(random.uniform(*BEKLE))
        ilk = False
        say['istek'] += 1
        try:
            d = fetch(path, referer)
            ardisik = 0
            return d
        except Exception:
            say['hata'] += 1
            ardisik += 1
            return None

    for lig, yil in isler():
        anahtar = f'{lig}_{yil}'
        if anahtar in durum['lig_tamam']:
            continue
        if saat() - bas > butce_sn or ardisik >= ARDISIK_HATA:
            break
        d = iste(f'getLeagueData/{lig}/{yil}', f'league/{lig}/{yil}')
        if d is None:
            continue
        yaz_gz(kok / 'leagues' / f'{anahtar}.json.gz', d)
        mevcut = set(durum['bekleyen'])
        for m in d.get('dates') or []:
            mid = str(m.get('id'))
            if m.get('isResult') and mid not in mevcut and not (kok / 'matches' / f'{mid}.json.gz').exists():
                durum['bekleyen'].append(mid)
                mevcut.add(mid)
        durum['lig_tamam'].append(anahtar)
        say['lig'] += 1

    kalan = []
    for i, mid in enumerate(durum['bekleyen']):
        if saat() - bas > butce_sn or ardisik >= ARDISIK_HATA:
            kalan.extend(durum['bekleyen'][i:])
            break
        d = iste(f'getMatchData/{mid}', f'match/{mid}')
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
    p.add_argument('--durum-cikti', type=Path)
    a = p.parse_args()
    say = calistir(a.veri, a.butce_dk * 60)
    print(' '.join(f'{k}={v}' for k, v in say.items()))
    if a.durum_cikti:
        a.durum_cikti.write_text(f"bitti={say['bitti']}\ndurdu_hata={say['durdu_hata']}\n", encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
