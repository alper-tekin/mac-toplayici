"""Eksik maç toplayıcı: verilen FotMob maç kimliklerinin sayfasını (matchDetails) bir kez indirir.

Elle başlatılır (workflow `eksik.yml`). Kimlik listesi herkese açık depoda durmaz; veri deposunun `eksik-veri`
dalında `eksik/liste.txt` dosyasındadır (satır başına bir kimlik, `#` ile başlayan satırlar yok sayılır).
Yanıtlar olduğu gibi gzip'lenip aynı dala yazılır:
  eksik/matches/<maç>.json.gz     maç sayfası
  eksik/durum.json                vazgeçilen kimlikler (üç başarısız deneme)
Her tur süre bütçesi dolunca durur, bir sonraki turu workflow başlatır; liste bitince zincir durur.
Çıktıya yalnız sayılar basılır. İstekler arasında 3-4,5 sn beklenir; üst üste 5 hata olursa tur durur.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from gecmis import ARDISIK_HATA, BEKLE, yaz_gz
from toplayici import istek, json_oku, json_yaz

DENEME = 3


def liste_oku(path: Path) -> list[str]:
    if not path.exists():
        return []
    out, gorulen = [], set()
    for satir in path.read_text(encoding='utf-8-sig').splitlines():
        s = satir.strip()
        if s and not s.startswith('#') and s.isdigit() and s not in gorulen:
            out.append(s)
            gorulen.add(s)
    return out


def calistir(veri: Path, butce_sn: float, fetch=istek, sleep=time.sleep, saat=time.monotonic) -> dict:
    kok = veri / 'eksik'
    durum = json_oku(kok / 'durum.json', {'vazgec': {}})
    say = dict(istek=0, mac=0, hata=0)
    bas = saat()
    ardisik = 0
    ilk = True

    def kalanlar():
        return [m for m in liste_oku(kok / 'liste.txt')
                if not (kok / 'matches' / f'{m}.json.gz').exists() and durum['vazgec'].get(m, 0) < DENEME]

    for mid in kalanlar():
        if saat() - bas > butce_sn or ardisik >= ARDISIK_HATA:
            break
        if not ilk:
            sleep(random.uniform(*BEKLE))
        ilk = False
        say['istek'] += 1
        try:
            d = fetch('matchDetails', {'matchId': mid})
        except Exception:
            say['hata'] += 1
            ardisik += 1
            durum['vazgec'][mid] = durum['vazgec'].get(mid, 0) + 1
            continue
        ardisik = 0
        yaz_gz(kok / 'matches' / f'{mid}.json.gz', d)
        say['mac'] += 1

    kok.mkdir(parents=True, exist_ok=True)
    json_yaz(kok / 'durum.json', durum)
    say['bekleyen'] = len(kalanlar())
    say['vazgecildi'] = sum(1 for n in durum['vazgec'].values() if n >= DENEME)
    say['bitti'] = int(say['bekleyen'] == 0)
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
