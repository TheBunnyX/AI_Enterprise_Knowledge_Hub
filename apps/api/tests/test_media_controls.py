"""Administrator controls over image/video generation, OpenRouter reference prices, and sunken Thai vowels in generated PDFs."""
import io
import pytest
from hub import media, openrouter_sync, savings, thai_pdf
from hub.database import SessionLocal
from hub.models import AIModel


# ---- per-model option limits -------------------------------------------------------------------------------------

CATALOG = {'resolutions': ['1K', '2K', '4K'], 'aspect_ratios': ['1:1', '16:9', '21:9'], 'durations': [3, 5, 8]}


def test_apply_limits_narrows_what_the_model_offers():
    out = media.apply_limits(CATALOG, {'resolutions': ['1K', '2K'], 'aspect_ratios': ['16:9']})
    assert out['resolutions'] == ['1K', '2K'] and out['aspect_ratios'] == ['16:9'] and out['durations'] == [3, 5, 8]


def test_apply_limits_ignores_empty_or_unmatched_restrictions():
    assert media.apply_limits(CATALOG, {}) == CATALOG
    assert media.apply_limits(CATALOG, {'resolutions': []}) == CATALOG
    # the provider changed its list and nothing allowed is offered any more: do not leave users with no choice
    assert media.apply_limits(CATALOG, {'resolutions': ['8K']})['resolutions'] == ['1K', '2K', '4K']


def test_apply_limits_does_not_change_the_input():
    media.apply_limits(CATALOG, {'resolutions': ['1K']})
    assert CATALOG['resolutions'] == ['1K', '2K', '4K']


@pytest.mark.parametrize('options', [{'resolution': '4K'}, {'aspect_ratio': '21:9'}, {'seconds': 8}])
def test_check_limits_rejects_values_the_administrator_did_not_allow(options):
    limits = {'resolutions': ['1K', '2K'], 'aspect_ratios': ['1:1', '16:9'], 'durations': ['3', '5']}
    with pytest.raises(ValueError):
        media.check_limits(options, limits)


def test_check_limits_accepts_allowed_values_and_unrestricted_models():
    limits = {'resolutions': ['1K'], 'durations': [3, 5]}
    media.check_limits({'resolution': '1K', 'seconds': 5, 'aspect_ratio': '21:9'}, limits)  # ratio is not restricted
    media.check_limits({'resolution': '4K'}, {})
    media.check_limits({'resolution': '4K'}, None)


def test_image_only_video_models_are_detected_from_the_description():
    tbc = {'supported_frame_images': ['first_frame'], 'description': 'It supports image to video and is fast.'}
    assert media.image_only(tbc)
    assert not media.image_only({**tbc, 'description': 'Supports text-to-video and image to video.'})
    assert not media.image_only({**tbc, 'supported_frame_images': []})
    assert not media.image_only({'description': ''})


# ---- OpenRouter reference prices ---------------------------------------------------------------------------------

def test_video_price_is_the_cheapest_tier_in_usd_per_second():
    assert openrouter_sync._video_price({'pricing_skus': {'cents_per_video_output_second_480p': '0.5', 'cents_per_video_output_second_720p': '1'}}) == 0.005
    assert openrouter_sync._video_price({'pricing_skus': {'duration_seconds_720p': '0.0695', 'duration_seconds_360p': '0.0232'}}) == 0.0232
    assert openrouter_sync._video_price({'pricing_skus': {}}) is None
    assert openrouter_sync._video_price({'pricing_skus': {'x': 'abc', 'y': '-1'}}) is None


def add_models(*models):
    with SessionLocal() as db:
        for m in models:
            db.add(m)
        db.commit()


def test_diff_includes_media_models_only_when_prices_are_given(client):
    add_models(AIModel(name='Flux', provider='OpenRouter', api_id='bfl/flux', category='Image', input_price=0, output_price=0),
               AIModel(name='Clip', provider='OpenRouter', api_id='x/clip', category='Video', input_price=0, output_price=0.005))
    with SessionLocal() as db:
        assert openrouter_sync.diff(db, []) == []  # a manual check without media prices leaves image/video models alone
        rows = {r['api_id']: r for r in openrouter_sync.diff(db, [], {'bfl/flux': 0.008, 'x/clip': 0.005})}
    assert rows['bfl/flux']['status'] == 'changed' and rows['bfl/flux']['new_output'] == 0.008 and rows['bfl/flux']['unit'] == 'ภาพ'
    assert rows['x/clip']['status'] == 'same' and rows['x/clip']['unit'] == 'วินาที'


def test_apply_prices_updates_only_the_output_price_of_media_models(client):
    add_models(AIModel(name='Flux', provider='OpenRouter', api_id='bfl/flux', category='Image', input_price=0, output_price=0),
               AIModel(name='Gone', provider='OpenRouter', api_id='x/gone', category='Image', input_price=0, output_price=0.1))
    with SessionLocal() as db:
        done = openrouter_sync.apply_prices(db, [], media={'bfl/flux': 0.008, 'x/other': 1})
        assert [d['api_id'] for d in done] == ['bfl/flux']
        prices = {m.api_id: (m.input_price, m.output_price) for m in db.query(AIModel)}
    assert prices['bfl/flux'] == (0, 0.008) and prices['x/gone'] == (0, 0.1)  # missing from OpenRouter: left unchanged


# ---- cost estimate before generating ------------------------------------------------------------------------------

def test_estimate_prefers_history_then_falls_back_to_the_reference_price(client):
    add_models(AIModel(id='img', name='Flux', provider='OpenRouter', api_id='bfl/flux', category='Image', input_price=0, output_price=0.008),
               AIModel(id='vid', name='Clip', provider='OpenRouter', api_id='x/clip', category='Video', input_price=0, output_price=0.005),
               AIModel(id='free', name='Free', provider='OpenRouter', api_id='x/free', category='Image', input_price=0, output_price=0))
    with SessionLocal() as db:
        assert savings.estimate_cost(db, 't', 'img') == 0.008
        assert savings.estimate_cost(db, 't', 'vid') == 0.025  # USD per second x 5 seconds
        assert savings.estimate_cost(db, 't', 'free') is None


# ---- sunken vowels (สระจม) in generated PDFs -----------------------------------------------------------------------

def test_sink_replaces_the_vowel_only_after_letters_with_tails():
    assert thai_pdf.sink('ญุ ญู ฎุ ฎู ฏุ ฏู ฐุ ฐู') == 'ญ ญ ฎ ฎ ฏ ฏ ฐ ฐ'
    assert thai_pdf.sink('บุญ ผู้ คุณ ปัญญา') == 'บุญ ผู้ คุณ ปัญญา'


def test_generated_pdf_keeps_sunken_vowels_searchable():
    from pypdf import PdfReader
    from hub.generated import build_pdf
    pdf = build_pdf({'title': 'ทดสอบ', 'sections': [{'heading': 'ตัวอย่าง', 'paragraphs': ['ญุ ญู ฐุ ฐู ปัญญา']}]})
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert 'ญุ ญู ฐุ ฐู ปัญญา' in text
    assert not any('' <= c <= '' for c in text)  # private-use codes never leak into extracted text


# ---- through the API -----------------------------------------------------------------------------------------------

import json
import httpx
from conftest import login_as
from hub import media as media_module, savings as savings_module

PNG = ('frame.png', b'PNG-first-frame', 'image/png')


def openrouter_video(admin, monkeypatch, *, limits=None, description='Text to video.', frames=('first_frame',)):
    monkeypatch.setenv('LITELLM_URL', 'http://gateway.test/v1')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    body = {'name': 'Clip', 'provider': 'OpenRouter', 'api_id': 'x/clip', 'category': 'Video', 'enabled': True}
    if limits:
        body['media_limits'] = limits
    model = admin.post('/api/admin/models', json=body)
    assert model.status_code in (200, 201), model.text
    info = {'id': 'x/clip', 'description': description, 'supported_resolutions': ['480p', '720p'], 'supported_aspect_ratios': ['16:9'],
            'supported_durations': [3, 5], 'supported_frame_images': list(frames)}
    original = httpx.Client
    def respond(request):
        if request.url.path.endswith('/videos/models'):
            return httpx.Response(200, json={'data': [info]})
        if request.url.path.endswith('/videos') and request.method == 'POST':
            return httpx.Response(200, json={'id': 'job-1', 'status': 'queued'})
        if request.url.path.endswith('/content'):
            return httpx.Response(200, content=b'mp4')
        return httpx.Response(200, json={'status': 'completed', 'usage': {'cost': 0.015}})
    monkeypatch.setattr(media_module.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    media_module._options_cache.clear()
    return model.json()['id']


def job(model, **opts):
    return {'kind': 'video', 'model_id': model, 'prompt': 'a cat', 'options': json.dumps({'aspect_ratio': '16:9', 'seconds': 3, **opts})}


def test_server_rejects_options_outside_the_models_limits(admin, monkeypatch):
    model = openrouter_video(admin, monkeypatch, limits={'resolutions': ['480p']})
    assert admin.post('/api/media/jobs', data=job(model, resolution='720p')).status_code == 422
    assert admin.post('/api/media/jobs', data=job(model, resolution='480p')).status_code == 202


def test_members_see_only_allowed_options_and_cannot_ask_for_the_full_list(admin, monkeypatch):
    model = openrouter_video(admin, monkeypatch, limits={'resolutions': ['480p']})
    assert admin.get('/api/media/model-options', params={'model_id': model, 'raw': True}).json()['resolutions'] == ['480p', '720p']
    login_as(admin, 'member')
    assert admin.get('/api/media/model-options', params={'model_id': model}).json()['resolutions'] == ['480p']
    assert admin.get('/api/media/model-options', params={'model_id': model, 'raw': True}).json()['resolutions'] == ['480p']


def test_image_to_video_models_need_a_first_frame(admin, monkeypatch):
    model = openrouter_video(admin, monkeypatch, description='Supports image to video only.')
    assert admin.get('/api/media/model-options', params={'model_id': model}).json()['requires_image'] is True
    r = admin.post('/api/media/jobs', data=job(model))
    assert r.status_code == 422 and 'เฟรมแรก' in r.json()['detail']
    assert admin.post('/api/media/jobs', data=job(model), files={'file': PNG}).status_code == 202


def test_text_to_video_models_do_not_need_a_frame(admin, monkeypatch):
    model = openrouter_video(admin, monkeypatch, description='Generates video from text.')
    assert admin.get('/api/media/model-options', params={'model_id': model}).json()['requires_image'] is False
    assert admin.post('/api/media/jobs', data=job(model)).status_code == 202


def test_daily_media_budget_blocks_further_jobs(admin, monkeypatch):
    model = openrouter_video(admin, monkeypatch, description='Generates video from text.')
    base = {k: v for k, v in savings_module.DEFAULTS.items()}
    assert admin.put('/api/savings/policy', json=base | {'media_daily_usd': 0.02}).status_code == 200
    assert admin.post('/api/media/jobs', data=job(model)).status_code == 202  # no history yet, so nothing is reserved
    done = admin.get('/api/media/jobs').json()[0]
    assert done['status'] == 'completed' and done['cost'] == 0.015
    # 0.015 spent + 0.015 estimated for the next job is over the 0.02 cap
    blocked = admin.post('/api/media/jobs', data=job(model))
    assert blocked.status_code == 429 and 'งบสร้างสื่อวันนี้' in blocked.json()['detail']
    assert admin.get('/api/media/estimate', params={'model_id': model}).json()['spent_today'] == 0.015
    assert admin.put('/api/savings/policy', json=base | {'media_daily_usd': 0.05}).status_code == 200
    assert admin.post('/api/media/jobs', data=job(model)).status_code == 202
    assert admin.put('/api/savings/policy', json=base | {'media_daily_usd': 0}).status_code == 200  # 0 = unlimited
    assert admin.post('/api/media/jobs', data=job(model)).status_code == 202
