from PIL import Image, ImageDraw
from session_watch.visual import compare_images


def test_identical_images(tmp_path):
    p=tmp_path/'a.png';Image.new('RGB',(100,100),'white').save(p)
    assert compare_images(p,p,tmp_path/'diff.png')['classification']=='visually_unchanged'


def test_changed_region_and_size(tmp_path):
    a,b=tmp_path/'a.png',tmp_path/'b.png'
    Image.new('RGB',(100,100),'white').save(a)
    image=Image.new('RGB',(100,100),'white');ImageDraw.Draw(image).rectangle((10,10,19,19),fill='black');image.save(b)
    result=compare_images(a,b,tmp_path/'diff.png')
    assert result['classification']=='visual_change'
    assert result['changed_percent']==1
    assert result['bounding_box']==(10,10,20,20)
    Image.new('RGB',(100,110),'white').save(b)
    assert compare_images(a,b,tmp_path/'diff.png')['dimensions_changed']


def test_pixel_noise_tolerance(tmp_path):
    a,b=tmp_path/'a.png',tmp_path/'b.png'
    Image.new('RGB',(100,100),(255,255,255)).save(a)
    Image.new('RGB',(100,100),(250,250,250)).save(b)
    assert compare_images(a,b,tmp_path/'diff.png')['changed_pixels']==0
