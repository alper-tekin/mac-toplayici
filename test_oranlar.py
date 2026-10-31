import json

import oranlar as o


def test_dosyalar_ve_manifest(tmp_path):
    istenen = []

    def fetch(url):
        istenen.append(url)
        if url.endswith('/2627/T1.csv'):
            raise RuntimeError('HTTP 404')
        if url.endswith('/2223/B1.csv'):
            return b'<html>not found</html>'
        if url.endswith('/2627/E0.csv'):
            return b'\xef\xbb\xbfDiv,Date,HomeTeam,AwayTeam\n'
        return b'Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH\nE0,01/01/25,A,B,1,0,2.1\n'

    bekle = []
    say = o.calistir(tmp_path, fetch=fetch, sleep=bekle.append)
    n = len(o.LIGLER) * len(o.SEZONLAR)
    assert len(istenen) == n and len(bekle) == n - 1
    assert say == dict(alindi=n - 2, hata=1, bos=1, bos_ilk=['3c68746d'])
    assert (tmp_path / 'oranlar' / '2627' / 'E0.csv').exists()
    assert (tmp_path / 'oranlar' / '2526' / 'E0.csv').read_bytes().startswith(b'Div,')
    assert not (tmp_path / 'oranlar' / '2223' / 'B1.csv').exists()
    m = json.loads((tmp_path / 'oranlar' / 'manifest.json').read_text(encoding='utf-8'))
    assert len(m) == n - 2 and len(m['2526/E0']['sha256']) == 64


def test_hic_alinamazsa_manifest_yazilmaz(tmp_path):
    def fetch(url):
        raise RuntimeError('zaman aşımı')

    say = o.calistir(tmp_path, fetch=fetch, sleep=lambda s: None)
    assert say['alindi'] == 0
    assert not (tmp_path / 'oranlar').exists()
