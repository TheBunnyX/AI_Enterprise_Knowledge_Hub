from hub.chat_service import vague


def test_vague_questions():
    for q in ['5+5', 'ทดสอบ', 'Test', ' สวัสดี! ', '???', '12345', 'hello']:
        assert vague(q), q


def test_real_questions_are_not_vague():
    for q in ['ลาป่วย', 'ข้อร้องเรียนระดับ 3 คืออะไร', 'VPN', 'ทดสอบกู้คืนระบบทุกกี่เดือน']:
        assert not vague(q), q
