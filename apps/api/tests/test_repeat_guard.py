from hub.repeat_guard import trim, Watch

BLOCK = 'หากต้องการทราบข้อมูลเพิ่มเติมเกี่ยวกับการสื่อสารกับลูกค้า สามารถสอบถามได้ที่ฝ่ายคุณภาพ '


def test_three_copies_shrink_to_one():
    text, looped = trim('คำตอบปกติ จบแล้ว ' + BLOCK * 3)
    assert looped and text == 'คำตอบปกติ จบแล้ว ' + BLOCK


def test_normal_text_is_untouched():
    text = 'ลาพักร้อนได้สิบวันต่อปี และต้องแจ้งล่วงหน้าเจ็ดวัน ตามนโยบายของบริษัท ' * 2 + 'ฝ่ายบุคคลเป็นผู้อนุมัติ'
    assert trim(text) == (text, False)


def test_watch_scans_in_steps():
    w = Watch(step=50)
    assert w.looped('a') == ('a', False)
    out, looped = w.looped('x' + BLOCK * 3)
    assert looped and out == 'x' + BLOCK
