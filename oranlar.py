"""football-data.co.uk sezon CSV'lerini (sonuç + kapanış oranları) bir veri klasörüne olduğu gibi yazar.

Elle çalıştırılır (workflow `oranlar.yml`). Her dosya bir kez istenir, aralarında 3 sn beklenir.
Çıktı: oranlar/<sezon>/<lig>.csv ve oranlar/manifest.json (boyut, sha256, alınma zamanı). Çıktıya yalnız sayılar basılır.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://www.football-data.co.uk/mmz4281'
LIGLER = ['E0', 'SP1', 'I1', 'D1', 'F1', 'N1', 'B1', 'P1', 'T1']
SEZONLAR = ['2223', '2324', '2425', '2526', '2627']
BEKLE = 3.0


def indir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'mac-toplayici (kisisel, ticari olmayan)'})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f'HTTP {r.status}')
        return r.read()


def calistir(veri: Path, fetch=indir, sleep=time.sleep) -> dict:
    kok = veri / 'oranlar'
    manifest_yol = kok / 'manifest.json'
    manifest = json.loads(manifest_yol.read_text(encoding='utf-8')) if manifest_yol.exists() else {}
    say = dict(alindi=0, hata=0, bos=0)
    ilk = True
    for sezon in SEZONLAR:
        for lig in LIGLER:
            if not ilk:
                sleep(BEKLE)
            ilk = False
            try:
                data = fetch(f'{BASE}/{sezon}/{lig}.csv')
            except Exception:
                say['hata'] += 1
                continue
            if not data.removeprefix(b'\xef\xbb\xbf').lstrip().startswith(b'Div'):   # yeni sezon dosyaları BOM'lu
                say['bos'] += 1
                say['bos_ilk'] = sorted({*say.get('bos_ilk', []), data[:4].hex()})   # yalnız ilk 4 bayt, tanı için
                continue
            yol = kok / sezon / f'{lig}.csv'
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_bytes(data)
            manifest[f'{sezon}/{lig}'] = dict(boyut=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                              alindi=datetime.now(timezone.utc).isoformat())
            say['alindi'] += 1
    if say['alindi']:
        kok.mkdir(parents=True, exist_ok=True)
        manifest_yol.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    return say


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--veri', type=Path, required=True, help='Veri dalının çalışma kopyası')
    say = calistir(p.parse_args().veri)
    print(' '.join(f'{k}={v}' for k, v in say.items()))
    return 0 if say['alindi'] else 1


if __name__ == '__main__':
    sys.exit(main())
