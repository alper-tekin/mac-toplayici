import gzip
import json

import eksik as e


class Fake:
    def __init__(self, hata=()):
        self.hata = set(hata)
        self.calls = []

    def __call__(self, path, params):
        self.calls.append(params['matchId'])
        if params['matchId'] in self.hata:
            raise RuntimeError('HTTP 500')
        return {'content': {'matchId': params['matchId']}}


class Saat:
    def __init__(self, adim):
        self.t, self.adim = 0.0, adim

    def __call__(self):
        self.t += self.adim
        return self.t


def liste(tmp_path, *ids):
    (tmp_path / 'eksik').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'eksik' / 'liste.txt').write_text('﻿# baslik\n' + '\n'.join(ids) + '\n', encoding='utf-8')


def test_listeyi_toplar_tekrari_atlar_ve_biter(tmp_path):
    liste(tmp_path, '11', '12', '11', 'abc', '')
    f = Fake()
    say = e.calistir(tmp_path, 1e9, fetch=f, sleep=lambda s: None, saat=Saat(0))
    assert f.calls == ['11', '12']
    assert say['mac'] == 2 and say['bitti'] == 1
    with gzip.open(tmp_path / 'eksik' / 'matches' / '12.json.gz', 'rt', encoding='utf-8') as fh:
        assert json.load(fh) == {'content': {'matchId': '12'}}
    f2 = Fake()
    say = e.calistir(tmp_path, 1e9, fetch=f2, sleep=lambda s: None, saat=Saat(0))
    assert f2.calls == [] and say['bitti'] == 1


def test_butce_dolunca_durur_sonra_devam_eder(tmp_path):
    liste(tmp_path, '1', '2', '3')
    say = e.calistir(tmp_path, 1.5, fetch=Fake(), sleep=lambda s: None, saat=Saat(1))
    assert say['mac'] == 1 and say['bekleyen'] == 2 and say['bitti'] == 0
    say = e.calistir(tmp_path, 1e9, fetch=Fake(), sleep=lambda s: None, saat=Saat(0))
    assert say['bitti'] == 1


def test_uc_hatada_vazgecer(tmp_path):
    liste(tmp_path, '7', '8')
    for _ in range(3):
        say = e.calistir(tmp_path, 1e9, fetch=Fake(hata={'7'}), sleep=lambda s: None, saat=Saat(0))
    assert say['vazgecildi'] == 1 and say['bitti'] == 1
    assert (tmp_path / 'eksik' / 'matches' / '8.json.gz').exists()


def test_ust_uste_hatada_durur(tmp_path):
    liste(tmp_path, *[str(i) for i in range(10)])
    say = e.calistir(tmp_path, 1e9, fetch=Fake(hata={str(i) for i in range(10)}), sleep=lambda s: None, saat=Saat(0))
    assert say['istek'] == e.ARDISIK_HATA and say['durdu_hata'] == 1


def test_liste_yoksa_biter(tmp_path):
    say = e.calistir(tmp_path, 1e9, fetch=Fake(), sleep=lambda s: None, saat=Saat(0))
    assert say['bitti'] == 1 and say['istek'] == 0
