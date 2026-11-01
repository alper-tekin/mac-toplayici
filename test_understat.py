import gzip
import json

import understat as u


class Fake:
    def __init__(self, hata=()):
        self.hata = set(hata)
        self.calls = []

    def __call__(self, path, referer):
        self.calls.append(path)
        if path in self.hata:
            raise RuntimeError('HTTP 500')
        if path.startswith('getLeagueData/'):
            _, lig, yil = path.split('/')
            return {'dates': [{'id': f'{lig}{yil}1', 'isResult': True}, {'id': f'{lig}{yil}2', 'isResult': True},
                              {'id': f'{lig}{yil}3', 'isResult': False}]}
        return {'shots': {'h': [], 'a': []}, 'mid': path.split('/')[1]}


class Saat:
    def __init__(self, adim):
        self.t, self.adim = 0.0, adim

    def __call__(self):
        self.t += self.adim
        return self.t


def test_tamamini_toplar_ve_biter(tmp_path):
    say = u.calistir(tmp_path, 1e9, fetch=Fake(), sleep=lambda s: None, saat=Saat(0))
    n = len(u.isler())
    assert say['lig'] == n and say['mac'] == 2 * n and say['bitti'] == 1
    d = json.loads(gzip.decompress((tmp_path / 'understat' / 'matches' / 'EPL20191.json.gz').read_bytes()))
    assert d['mid'] == 'EPL20191'
    f2 = Fake()
    assert u.calistir(tmp_path, 1e9, fetch=f2, sleep=lambda s: None, saat=Saat(0))['bitti'] == 1 and f2.calls == []


def test_butce_ve_devam(tmp_path):
    toplam = 0
    while True:
        s = u.calistir(tmp_path, 10.5, fetch=Fake(), sleep=lambda s: None, saat=Saat(1))
        toplam += s['mac']
        if s['bitti']:
            break
    assert toplam == 2 * len(u.isler())


def test_ardisik_hatada_durur(tmp_path):
    f = Fake(hata={f'getLeagueData/{l}/{y}' for l, y in u.isler()})
    say = u.calistir(tmp_path, 1e9, fetch=f, sleep=lambda s: None, saat=Saat(0))
    assert say['durdu_hata'] == 1 and say['istek'] == u.ARDISIK_HATA
