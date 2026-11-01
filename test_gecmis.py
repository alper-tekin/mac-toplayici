import gzip
import json

import gecmis as g


def lig_yaniti(lig, sez):
    def mac(i, finished=True):
        return {'id': f'{lig}{sez[:4]}{i}', 'home': {'name': 'A'}, 'away': {'name': 'B'},
                'status': {'finished': finished}}
    return {'fixtures': {'allMatches': [mac(1), mac(2), mac(3, finished=False)]}}


class Fake:
    def __init__(self, hata=()):
        self.hata = set(hata)
        self.calls = []

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        key = params.get('matchId') or (params['id'], params['season'])
        if key in self.hata:
            raise RuntimeError('HTTP 500')
        if path == 'leagues':
            return lig_yaniti(params['id'], params['season'])
        return {'content': {'matchId': params['matchId']}}


class Saat:
    def __init__(self, adim):
        self.t, self.adim = 0.0, adim

    def __call__(self):
        self.t += self.adim
        return self.t


def test_tamamini_toplar_ve_biter(tmp_path):
    f = Fake()
    say = g.calistir(tmp_path, 1e9, fetch=f, sleep=lambda s: None, saat=Saat(0))
    n_is = len(g.isler())
    assert say['lig'] == n_is and say['mac'] == 2 * n_is and say['bitti'] == 1
    assert (tmp_path / 'gecmis' / 'leagues' / '47_2019-2020.json.gz').exists()
    assert not (tmp_path / 'gecmis' / 'leagues' / '10216_2020-2021.json.gz').exists()   # KL yok
    one = json.loads(gzip.decompress((tmp_path / 'gecmis' / 'matches' / '4720191.json.gz').read_bytes()))
    assert one['content']['matchId'] == '4720191'
    # ikinci tur hiçbir şey istemez
    f2 = Fake()
    say2 = g.calistir(tmp_path, 1e9, fetch=f2, sleep=lambda s: None, saat=Saat(0))
    assert f2.calls == [] and say2['bitti'] == 1


def test_butce_dolunca_kaldigi_yerden_devam(tmp_path):
    f = Fake()
    say = g.calistir(tmp_path, 10.5, fetch=f, sleep=lambda s: None, saat=Saat(1))
    assert say['bitti'] == 0
    toplam = say['mac']
    while True:
        s = g.calistir(tmp_path, 10.5, fetch=Fake(), sleep=lambda s: None, saat=Saat(1))
        toplam += s['mac']
        if s['bitti']:
            break
    assert toplam == 2 * len(g.isler())


def test_hatali_mac_uc_denemeden_sonra_birakilir(tmp_path):
    f = Fake(hata={'4720191'})
    for _ in range(3):
        say = g.calistir(tmp_path, 1e9, fetch=f, sleep=lambda s: None, saat=Saat(0))
    d = json.loads((tmp_path / 'gecmis' / 'durum.json').read_text(encoding='utf-8'))
    assert d['vazgec']['4720191'] == 3 and '4720191' not in d['bekleyen'] and say['bitti'] == 1


def test_ardisik_hatada_durur(tmp_path):
    f = Fake(hata={(l, s) for l, s in g.isler()})
    say = g.calistir(tmp_path, 1e9, fetch=f, sleep=lambda s: None, saat=Saat(0))
    assert say['durdu_hata'] == 1 and say['istek'] == g.ARDISIK_HATA
