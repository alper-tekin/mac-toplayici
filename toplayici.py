"""FotMob maç toplayıcı: muhtemel kadro, ilk 11 ve maç sonu verisini sıkıştırılmış JSON olarak bir veri klasörüne yazar.

Veri klasörü özel bir deponun veri dalıdır; bu depoya hiçbir veri yazılmaz. Çıktıya yalnız sayılar basılır.

Takvim (her tur 5 dk'da bir; öncelik bu sırayla, turdaki istek sınırı dolarsa kalanı sonraki tura):
  muhtemel  her saat bir kez, o günün (İstanbul) başlamamış maçları  -> muhtemel/<gün>/<maç>_<saat>.json.gz
  ilk11     başlamaya 55..0 dk kala, resmi 11 gelene kadar her tur       -> ilk11/<maç>.json.gz
  mac       başlamadan 3 saat sonra, 15 dk arayla, veri tamamlanana dek  -> mac/<maç>.json.gz
            (24 saatte tamamlanmazsa bitmişse olduğu gibi, `eksik` işaretiyle)
  lig       her ligin fikstürü günde bir kez                             -> lig/<lig>.json.gz
  gelecek   önümüzdeki 14 günün maç sayfası: yeni/değişmiş olan, 2 gün içindekiler 12 saatte bir
                                                                           -> gelecek/<maç>.json.gz
Bu kayıtlar veri deposundaki günlük güncellemenin FotMob yerine okuduğu kaynaktır.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = 'https://www.fotmob.com/api/data'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.fotmob.com/',
}
TZ = ZoneInfo('Europe/Istanbul')
FIKSTUR_ARALIK = timedelta(minutes=55)
ILK11_ONCE = timedelta(minutes=55)
MAC_SONRA = timedelta(hours=3)
MAC_ARALIK = timedelta(minutes=15)
MAC_VAZGEC = timedelta(hours=24)
SAKLAMA = timedelta(days=21)
GELECEK_GUN = timedelta(days=14)
GELECEK_GERI = timedelta(days=2)       # ertelenmiş/oynanmamış yakın geçmiş de güncellemenin seçimine girer
GELECEK_YAKIN = timedelta(days=2)
GELECEK_YENILE = timedelta(hours=12)
ISTEK_SINIRI = 80          # bir turda en çok FotMob isteği


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def istek(path: str, params: dict) -> dict:
    from curl_cffi import requests
    r = requests.get(f'{BASE}/{path}', params=params, headers=HEADERS, impersonate='chrome', timeout=30,
                     verify=os.environ.get('TOPLAYICI_CA') or True)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}')
    data = r.json()
    if not isinstance(data, dict) or not data:
        raise RuntimeError('boş yanıt')
    return data


def yaz(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with gzip.open(tmp, 'wt', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
    tmp.replace(path)


def json_oku(path: Path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def json_yaz(path: Path, value) -> None:
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    tmp.replace(path)


def resmi_11(detail: dict) -> bool:
    lineup = (detail.get('content') or {}).get('lineup') or {}
    return lineup.get('lineupType') == 'standard' and all(
        len((lineup.get(side) or {}).get('starters') or []) == 11 for side in ('homeTeam', 'awayTeam'))


def tamam(detail: dict) -> bool:
    status = (detail.get('header') or {}).get('status') or {}
    content = detail.get('content') or {}
    return bool(status.get('finished')) and all(content.get(k) for k in ('stats', 'playerStats', 'shotmap'))


def sezon(now: datetime) -> str:
    """Veri deposundaki günlük güncellemeyle aynı sezon adı (Temmuz'da döner)."""
    y = now.year if now.month >= 7 else now.year - 1
    return f'{y}/{y + 1}'


_ATLA = {'overview', 'stats', 'table', 'transfers', 'details', 'seostr', 'QAData', 'tabs', 'seasons', 'allAvailableSeasons'}


def mac_nesneleri(obj) -> list[dict]:
    """Lig/turnuva yanıtının her seviyesindeki maç nesneleri ('id' ya da 'matchId' + takım adları + status)."""
    seen, out = set(), []

    def walk(o, top=False):
        if isinstance(o, dict):
            mid = o.get('id', o.get('matchId'))
            home, away = o.get('home'), o.get('away')
            if (mid is not None and isinstance(home, dict) and home.get('name') and isinstance(away, dict)
                    and away.get('name') and isinstance(o.get('status'), dict)):
                if str(mid) not in seen:
                    seen.add(str(mid))
                    out.append(o if 'id' in o else {**o, 'id': mid})
                return
            for k, v in o.items():
                if not (top and k in _ATLA):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj, top=True)
    return out


def imza(m: dict) -> str:
    """Fikstür satırının değişip değişmediği (günlük güncellemedeki imzayla aynı alanlar)."""
    status = m.get('status') or {}
    keep = {k: m.get(k) for k in ['id', 'home', 'away', 'round', 'roundName']}
    keep['status'] = {k: status.get(k) for k in ['utcTime', 'finished', 'started', 'cancelled', 'awarded', 'scoreStr', 'reason']}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def kadro_ozeti(detail: dict, now: datetime) -> dict:
    """Kadroya çevirmek için yeterli kısım: maç kimliği (general), takımlar ve durum (header), kadro."""
    content = detail.get('content') or {}
    header = detail.get('header') or {}
    return dict(alindi=now.isoformat(), status=header.get('status'), general=detail.get('general'), header=header,
                lineup=content.get('lineup'))


class Tur:
    def __init__(self, veri: Path, now: datetime, fetch=istek, sleep=time.sleep):
        self.veri, self.now, self.fetch, self.sleep = veri, now, fetch, sleep
        self.ligler = {int(x) for x in json_oku(veri / 'ligler.json', [])}
        self.durum = json_oku(veri / 'durum.json', {'maclar': {}})
        self.say = dict(istek=0, fikstur=0, muhtemel=0, ilk11=0, mac=0, mac_eksik=0, vazgecildi=0, lig=0, gelecek=0,
                        hata=0, silindi=0)
        self.yeni_ilk11: list[str] = []
        self._detay: dict[str, dict] = {}

    def _istek(self, path, params):
        if self.say['istek'] >= ISTEK_SINIRI:
            raise LimitError
        if self.say['istek']:
            self.sleep(random.uniform(2, 4))
        self.say['istek'] += 1
        return self.fetch(path, params)

    def detay(self, mid: str) -> dict:
        if mid not in self._detay:
            self._detay[mid] = self._istek('matchDetails', {'matchId': mid})
        return self._detay[mid]

    def fikstur(self) -> None:
        try:
            self._fikstur()
        except LimitError:
            raise
        except Exception:
            self.say['hata'] += 1   # eldeki durumla devam; sonraki tur yeniden dener

    def _fikstur(self) -> None:
        son = self.durum.get('fikstur_at')
        if son and self.now - utc(son) < FIKSTUR_ARALIK:
            return
        maclar = self.durum['maclar']
        for gun in (-1, 0, 1):
            tarih = (self.now + timedelta(days=gun)).strftime('%Y%m%d')
            data = self._istek('matches', {'date': tarih})
            for lig in data.get('leagues') or []:
                lig_id = lig.get('primaryId') or lig.get('id')
                if lig_id not in self.ligler:
                    continue
                for m in lig.get('matches') or []:
                    status = m.get('status') or {}
                    mid = str(m['id'])
                    if status.get('cancelled') or not status.get('utcTime'):
                        if mid in maclar and not maclar[mid].get('mac_alindi'):
                            del maclar[mid]
                        continue
                    kayit = maclar.setdefault(mid, dict(lig=lig_id, muhtemel=[], ilk11=None, mac_alindi=None,
                                                        mac_deneme=0, mac_son=None, vazgecildi=False))
                    kayit['ko'] = utc(status['utcTime']).isoformat()
            self.say['fikstur'] += 1
        self.durum['fikstur_at'] = self.now.isoformat()

    def isler(self) -> None:
        bugun = self.now.astimezone(TZ).date()
        saat = self.now.astimezone(TZ).strftime('%H')
        for mid, k in sorted(self.durum['maclar'].items(), key=lambda kv: kv[1]['ko']):
            ko = utc(k['ko'])
            try:
                if ko - ILK11_ONCE <= self.now < ko and not k['ilk11']:
                    d = self.detay(mid)
                    if resmi_11(d):
                        yaz(self.veri / 'ilk11' / f'{mid}.json.gz', dict(alindi=self.now.isoformat(), ko=k['ko'], detay=d))
                        k['ilk11'] = self.now.isoformat()
                        self.yeni_ilk11.append(mid)
                        self.say['ilk11'] += 1
                if (self.now < ko and ko.astimezone(TZ).date() == bugun and saat not in k['muhtemel']
                        and not k['ilk11']):
                    d = self.detay(mid)
                    if (d.get('content') or {}).get('lineup'):
                        gun = ko.astimezone(TZ).strftime('%Y-%m-%d')
                        yaz(self.veri / 'muhtemel' / gun / f'{mid}_{saat}.json.gz', kadro_ozeti(d, self.now))
                        self.say['muhtemel'] += 1
                    k['muhtemel'].append(saat)
                if self.now >= ko + MAC_SONRA and not k['mac_alindi'] and not k['vazgecildi']:
                    if self.now >= ko + MAC_VAZGEC:
                        d = self.detay(mid)
                        if ((d.get('header') or {}).get('status') or {}).get('finished'):
                            eksik = not tamam(d)
                            yaz(self.veri / 'mac' / f'{mid}.json.gz',
                                dict(alindi=self.now.isoformat(), ko=k['ko'], eksik=eksik, detay=d))
                            k['mac_alindi'] = self.now.isoformat()
                            self.say['mac_eksik' if eksik else 'mac'] += 1
                        else:
                            k['vazgecildi'] = True
                            self.say['vazgecildi'] += 1
                    elif not k['mac_son'] or self.now - utc(k['mac_son']) >= MAC_ARALIK:
                        k['mac_son'] = self.now.isoformat()
                        k['mac_deneme'] += 1
                        d = self.detay(mid)
                        if tamam(d):
                            yaz(self.veri / 'mac' / f'{mid}.json.gz', dict(alindi=self.now.isoformat(), ko=k['ko'], detay=d))
                            k['mac_alindi'] = self.now.isoformat()
                            self.say['mac'] += 1
            except LimitError:
                raise
            except Exception:
                self.say['hata'] += 1

    def lig_fiksturleri(self) -> None:
        gun = self.now.astimezone(TZ).strftime('%Y-%m-%d')
        alinan = self.durum.setdefault('lig', {})
        aday = self.durum.setdefault('gelecek_aday', {})
        for lig in sorted(self.ligler):
            if alinan.get(str(lig)) == gun:
                continue
            try:
                s = sezon(self.now)
                data = self._istek('leagues', {'id': lig, 'season': s})
                yaz(self.veri / 'lig' / f'{lig}.json.gz', dict(alindi=self.now.isoformat(), sezon=s, veri=data))
                for m in mac_nesneleri(data):
                    mid, status = str(m['id']), m.get('status') or {}
                    ko = utc(status['utcTime']) if status.get('utcTime') else None
                    if (ko is None or status.get('finished') or status.get('cancelled') or status.get('awarded')
                            or not self.now - GELECEK_GERI <= ko <= self.now + GELECEK_GUN):
                        aday.pop(mid, None)
                    else:
                        aday[mid] = dict(imza=imza(m), ko=ko.isoformat(), lig=lig)
                alinan[str(lig)] = gun
                self.say['lig'] += 1
            except LimitError:
                raise
            except Exception:
                self.say['hata'] += 1

    def gelecek(self) -> None:
        alinan = self.durum.setdefault('gelecek', {})
        for mid, a in sorted(self.durum.get('gelecek_aday', {}).items(), key=lambda kv: kv[1]['ko']):
            k, ko = alinan.get(mid), utc(a['ko'])
            if not (k is None or k['imza'] != a['imza']
                    or (ko - self.now <= GELECEK_YAKIN and self.now - utc(k['alindi']) >= GELECEK_YENILE)):
                continue
            try:
                d = self.detay(mid)
                yaz(self.veri / 'gelecek' / f'{mid}.json.gz',
                    dict(alindi=self.now.isoformat(), ko=a['ko'], imza=a['imza'], detay=d))
                alinan[mid] = dict(imza=a['imza'], alindi=self.now.isoformat(), ko=a['ko'])
                self.say['gelecek'] += 1
            except LimitError:
                raise
            except Exception:
                self.say['hata'] += 1

    def temizle(self) -> None:
        sinir = self.now - SAKLAMA
        for mid, k in list(self.durum['maclar'].items()):
            if utc(k['ko']) < sinir:
                for p in (self.veri / 'ilk11' / f'{mid}.json.gz', self.veri / 'mac' / f'{mid}.json.gz'):
                    p.unlink(missing_ok=True)
                del self.durum['maclar'][mid]
                self.say['silindi'] += 1
        aday = self.durum.get('gelecek_aday', {})
        for mid, a in list(aday.items()):
            if utc(a['ko']) < self.now - GELECEK_GERI:
                del aday[mid]
        for mid, k in list(self.durum.get('gelecek', {}).items()):
            if mid not in aday and utc(k['ko']) < self.now - GELECEK_GERI:
                (self.veri / 'gelecek' / f'{mid}.json.gz').unlink(missing_ok=True)
                del self.durum['gelecek'][mid]
        kok = self.veri / 'muhtemel'
        if kok.exists():
            for gun in kok.iterdir():
                if gun.is_dir() and gun.name < sinir.astimezone(TZ).strftime('%Y-%m-%d'):
                    shutil.rmtree(gun)

    def calistir(self) -> dict:
        try:
            self.fikstur()
            self.isler()
            self.lig_fiksturleri()
            self.gelecek()
        except LimitError:
            pass                    # kalan işler sonraki tura
        self.temizle()
        self.durum['son_tur'] = self.now.isoformat()
        json_yaz(self.veri / 'durum.json', self.durum)
        return self.say


class LimitError(Exception):
    pass


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--veri', type=Path, required=True)
    p.add_argument('--yeni-ilk11', type=Path, help='Bu turda alınan ilk 11 maç kimliklerinin yazılacağı dosya')
    a = p.parse_args()
    if not (a.veri / 'ligler.json').exists():
        print('ligler.json yok', file=sys.stderr)
        return 2
    tur = Tur(a.veri, datetime.now(timezone.utc))
    say = tur.calistir()
    if a.yeni_ilk11:
        a.yeni_ilk11.write_text('\n'.join(tur.yeni_ilk11), encoding='utf-8')
    print(' '.join(f'{k}={v}' for k, v in say.items()), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
