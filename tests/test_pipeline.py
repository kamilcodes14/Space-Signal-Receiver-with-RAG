import json
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from source import SimulatedSource, RTLSDRSource, FileSource
from detector import dedoppler_search, physical_candidates
from visualizer import plot_waterfall


@pytest.mark.parametrize('drift', [-0.4, 0, 0.4, 0.273])
def test_recovers_positive_negative_zero_and_off_grid_drift(drift):
    source = SimulatedSource(seed=42, signal_strength=5, drift_rate_hz_per_s=drift)
    f, t, p = source.capture()
    c = physical_candidates(dedoppler_search(p), f, t)[0]
    assert abs(c['start_freq_bin'] - source.truth['start_freq_bin']) <= 1
    assert abs(c['drift_rate_hz_per_s'] - drift) <= 2 / (len(t)-1)


def test_default_injection_has_resolvable_drift():
    a = SimulatedSource(seed=9)
    f, t, signal = a.capture()
    _, _, noise = SimulatedSource(seed=9, inject_signal=False).capture()
    assert np.unique(np.argmax(signal-noise, axis=1)).size > 40
    assert np.isclose((f[1]-f[0])*1e6, 1)


def test_noise_mean_is_centered_and_zero_variance_safe():
    # Deterministic smoke test only; multi-seed false-alarm rates are in the benchmark.
    _, _, p = SimulatedSource(seed=42, inject_signal=False).capture()
    assert dedoppler_search(p) == []
    assert dedoppler_search(np.ones((32,64))) == []


def test_truncated_tracks_require_minimum_coverage():
    p = np.ones((40,40)); p[np.arange(10), 30+np.arange(10)] = 100
    assert dedoppler_search(p, [1], n_sigma=2, min_coverage=.8) == []


@pytest.mark.parametrize('bad', [np.ones(5), np.full((2,2),np.nan), -np.ones((2,2))])
def test_rejects_invalid_power(bad):
    with pytest.raises(ValueError): dedoppler_search(bad)


def test_sdr_time_axis_uses_sample_clock(monkeypatch):
    class FakeSDR:
        def read_samples(self,n): return np.ones(n,dtype=complex)
        def close(self): self.closed=True
    monkeypatch.setitem(sys.modules, 'rtlsdr', SimpleNamespace(RtlSdr=FakeSDR))
    s = RTLSDRSource(n_time_steps=4)
    f,t,p = s.capture()
    assert np.allclose(np.diff(t), .001)
    assert p.shape == (4,2048)
    assert np.isclose((f[1]-f[0])*1e6,1000)
    s.close(); assert s.sdr.closed


def test_telescope_file_header_units_and_descending_axis(tmp_path):
    h5py = pytest.importorskip('h5py'); pytest.importorskip('blimpy')
    path = tmp_path/'small.h5'
    original = np.arange(32*16,dtype=np.float32).reshape(32,1,16)+1
    with h5py.File(path,'w') as h:
        h.attrs['CLASS']='FILTERBANK'; h.attrs['VERSION']='1.0'
        d=h.create_dataset('data',data=original)
        for k,v in dict(fch1=100.0,foff=-.000001,tsamp=2.5,nchans=16,nifs=1,nbits=32,
                        tstart=57000.0,source_name='SYNTHETIC_TEST',telescope_id=6,machine_id=0,data_type=1).items():
            d.attrs[k]=v
    f,t,p=FileSource(path,max_time_steps=32).capture()
    assert np.all(np.diff(f)>0)
    assert np.allclose(np.diff(t),2.5)
    assert np.array_equal(p,original[:,0,::-1])


def test_plot_creates_output_directory(tmp_path):
    f,t,p=SimulatedSource(n_time_steps=8,n_freq_bins=16,seed=1).capture()
    path=tmp_path/'nested'/'waterfall.png'
    plot_waterfall(f,t,p,out_path=path)
    assert path.read_bytes().startswith(b'\x89PNG')


def test_web_capture_and_invalid_seed():
    from app_web import app
    client=app.test_client()
    assert client.get('/signal').status_code==200
    r=client.post('/signal',data={'seed':'42','inject_signal':'on'})
    assert r.status_code==200 and b'Hz/s' in r.data and b'data:image/png' in r.data
    for seed in ['bad','-1','']:
        assert client.post('/signal',data={'seed':seed}).status_code==400


def test_cli_writes_machine_readable_run_log(tmp_path):
    import subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    log=tmp_path/'run.json'; image=tmp_path/'nested'/'waterfall.png'
    result=subprocess.run([sys.executable,str(root/'src'/'app.py'),'--seed','42',
                           '--log',str(log),'--out',str(image)],capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    data=json.loads(log.read_text())
    assert data['source']=='simulated'
    assert data['truth']['drift_rate_hz_per_s']==.4
    assert abs(data['candidates'][0]['drift_rate_hz_per_s']-.4)<.02
    assert image.exists()
