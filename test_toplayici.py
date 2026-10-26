import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest

import toplayici as t

KO = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)     # 19:00 İstanbul


def detail(lineup_type='predicted', finished=False, full=False):
    side = {'starters': [{}] * 11}
    content = {'lineup': {'lineupType': lineup_type, 'homeTeam': side, 'awayTeam': side}}
    if full:
        content.update(stats={'x': 1}, playerStats={'x': 1}, shotmap={'x': 1})
    return {'header': {'status': {'finished': finished}}, 'content': content}


class Fake:
    def __init__(self, details=None, ligler=None):
        self.details = details or {}
        self.ligler = ligler or {}
        self.calls = []

    def __call__(self, path, params):
        self.calls.append((path, params))
        if path == 'matches':
            return {'leagues': [
                {'id': 999, 'primaryId': 71, 'matches': [
                    {'id': 1, 'status': {'utcTime': '2026-10-26T16:00:00.000Z'}},
                    {'id': 2, 'status': {'utcTime': '2026-10-26T16:00:00.000Z', 'cancelled': True}}]},
                {'id': 5, 'primaryId': 5, 'matches': [{'id': 3, 'status': {'utcTime': '2026-10-26T16:00:00.000Z'}}]}]}
        if path == 'leagues':
            return self.ligler.get(params['id'], {'fixtures': {'allMatches': []}})
        return self.details[params['matchId']]


def tur(tmp_path, now, fake):
    (tmp_path / 'ligler.json').write_text('[71]')
    return t.Tur(tmp_path, now, fetch=fake, sleep=lambda s: None)


def oku(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return json.load(f)


def test_fikstur_lig_suzgeci_ve_iptal(tmp_path):
    x = tur(tmp_path, KO - timedelta(hours=5), Fake({'1': detail()}))
    x.calistir()
    assert set(x.durum['maclar']) == {'1'}
    assert x.say['fikstur'] == 3


def test_saatlik_muhtemel_bir_kez(tmp_path):
    now = KO - timedelta(hours=5)
    fake = Fake({'1': detail()})
    tur(tmp_path, now, fake).calistir()
    assert (tmp_path / 'muhtemel' / '2026-10-26' / '1_14.json.gz').exists()
    n = len(fake.calls)
    tur(tmp_path, now + timedelta(minutes=5), fake).calistir()
    assert len(fake.calls) == n                      # aynı saat: istek yok
    tur(tmp_path, now + timedelta(hours=1), fake).calistir()
    assert (tmp_path / 'muhtemel' / '2026-10-26' / '1_15.json.gz').exists()


def test_ilk11_yalniz_resmi_ve_pencerede(tmp_path):
    fake = Fake({'1': detail('predicted')})
    x = tur(tmp_path, KO - timedelta(minutes=50), fake)
    x.calistir()
    assert not (tmp_path / 'ilk11' / '1.json.gz').exists()
    fake.details['1'] = detail('standard')
    x = tur(tmp_path, KO - timedelta(minutes=45), fake)
    x.calistir()
    assert x.yeni_ilk11 == ['1']
    assert oku(tmp_path / 'ilk11' / '1.json.gz')['alindi'] == (KO - timedelta(minutes=45)).isoformat()
    n = len([c for c in fake.calls if c[0] == 'matchDetails'])
    tur(tmp_path, KO - timedelta(minutes=40), fake).calistir()
    assert len([c for c in fake.calls if c[0] == 'matchDetails']) == n   # alındı: tekrar yok, muhtemel de durur


def test_ilk11_pencere_disinda_istenmez(tmp_path):
    fake = Fake({'1': detail('standard')})
    x = tur(tmp_path, KO + timedelta(minutes=1), fake)
    x.calistir()
    assert not (tmp_path / 'ilk11').exists()


def test_mac_verisi_3_saat_sonra_15_dk_arayla(tmp_path):
    fake = Fake({'1': detail('standard', finished=True, full=False)})
    tur(tmp_path, KO + timedelta(hours=2, minutes=55), fake).calistir()
    assert not any(c[0] == 'matchDetails' for c in fake.calls)
    tur(tmp_path, KO + timedelta(hours=3), fake).calistir()
    tur(tmp_path, KO + timedelta(hours=3, minutes=5), fake).calistir()
    assert len([c for c in fake.calls if c[0] == 'matchDetails']) == 1   # 15 dk dolmadı
    fake.details['1'] = detail('standard', finished=True, full=True)
    x = tur(tmp_path, KO + timedelta(hours=3, minutes=15), fake)
    x.calistir()
    assert x.say['mac'] == 1 and (tmp_path / 'mac' / '1.json.gz').exists()
    assert x.durum['maclar']['1']['mac_deneme'] == 2


def test_24_saatte_vazgecilir(tmp_path):
    fake = Fake({'1': detail()})
    x = tur(tmp_path, KO + timedelta(hours=24), fake)
    x.calistir()
    assert x.durum['maclar']['1']['vazgecildi'] and not (tmp_path / 'mac').exists()


def test_istek_siniri_turu_bozmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'ISTEK_SINIRI', 2)
    x = tur(tmp_path, KO - timedelta(hours=5), Fake({'1': detail()}))
    x.calistir()
    assert x.say['istek'] == 2 and (tmp_path / 'durum.json').exists()


def test_eski_kayitlar_silinir(tmp_path):
    fake = Fake({'1': detail('standard', finished=True, full=True)})
    tur(tmp_path, KO + timedelta(hours=3), fake).calistir()
    assert (tmp_path / 'mac' / '1.json.gz').exists()
    x = tur(tmp_path, KO + timedelta(days=22), Fake())
    x.fetch = lambda p, q: {'leagues': []}
    x.calistir()
    assert not (tmp_path / 'mac' / '1.json.gz').exists() and '1' not in x.durum['maclar']


def test_hata_sayilir_ve_devam_eder(tmp_path):
    def fetch(path, params):
        if path in ('matches', 'leagues'):
            return Fake()(path, params)
        raise RuntimeError('HTTP 500')
    x = tur(tmp_path, KO - timedelta(hours=5), fetch)
    x.calistir()
    assert x.say['hata'] == 1


def fikstur_satiri(mid, ko, **status):
    return {'id': mid, 'home': {'name': 'A'}, 'away': {'name': 'B'}, 'status': dict(utcTime=ko, **status)}


def test_lig_fiksturu_gunde_bir_ve_gelecek_maclar(tmp_path):
    lig = {'fixtures': {'allMatches': [
        fikstur_satiri(10, '2026-10-30T18:00:00.000Z'),                 # 4 gün sonra: alınır
        fikstur_satiri(11, '2026-11-20T18:00:00.000Z'),                 # 14 günden uzak: alınmaz
        fikstur_satiri(12, '2026-10-20T18:00:00.000Z', finished=True),  # bitmiş: alınmaz
    ]}, 'details': {'name': 'x'}}
    fake = Fake({'1': detail(), '10': detail()}, {71: lig})
    now = KO - timedelta(hours=5)
    x = tur(tmp_path, now, fake)
    x.calistir()
    assert x.say['lig'] == 1 and x.say['gelecek'] == 1
    assert oku(tmp_path / 'lig' / '71.json.gz')['sezon'] == '2026/2027'
    assert oku(tmp_path / 'gelecek' / '10.json.gz')['detay'] == detail()
    y = tur(tmp_path, now + timedelta(hours=1), fake)
    y.calistir()
    assert y.say['lig'] == 0 and y.say['gelecek'] == 0          # aynı gün, değişmemiş, yakın değil
    lig['fixtures']['allMatches'][0]['status']['utcTime'] = '2026-10-31T18:00:00.000Z'   # saati değişti
    z = tur(tmp_path, now + timedelta(days=1), fake)
    z.calistir()
    assert z.say['lig'] == 1 and z.say['gelecek'] == 1


def test_gelecek_yakin_mac_12_saatte_yenilenir(tmp_path):
    lig = {'fixtures': {'allMatches': [fikstur_satiri(10, '2026-10-27T18:00:00.000Z')]}}
    fake = Fake({'1': detail(), '10': detail()}, {71: lig})
    tur(tmp_path, KO - timedelta(hours=5), fake).calistir()
    x = tur(tmp_path, KO + timedelta(hours=6), fake)                     # aynı gün değil ama 11 saat geçti
    x.calistir()
    assert x.say['gelecek'] == 0
    x = tur(tmp_path, KO + timedelta(hours=8), fake)                     # 13 saat
    x.calistir()
    assert x.say['gelecek'] == 1


def test_24_saatte_bitmis_eksik_mac_kaydedilir(tmp_path):
    fake = Fake({'1': detail('standard', finished=True, full=False)})
    x = tur(tmp_path, KO + timedelta(hours=24), fake)
    x.calistir()
    r = oku(tmp_path / 'mac' / '1.json.gz')
    assert r['eksik'] is True and x.say['mac_eksik'] == 1 and not x.durum['maclar']['1']['vazgecildi']


def test_mac_nesneleri_ic_ice_ve_matchid():
    data = {'details': {'x': fikstur_satiri(99, 'z')},
            'playoff': {'rounds': [{'matchups': [{'matchId': 5, 'home': {'name': 'A'}, 'away': {'name': 'B'}, 'status': {}}]}]},
            'fixtures': {'allMatches': [fikstur_satiri(1, 'z'), fikstur_satiri(1, 'z')]}}
    assert sorted(str(m['id']) for m in t.mac_nesneleri(data)) == ['1', '5']
