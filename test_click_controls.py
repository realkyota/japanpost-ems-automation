import unittest
from japanpost import Bot, UserError

class Collection:
    def __init__(self, elements=()): self.elements=list(elements)
    def count(self): return len(self.elements)
    def nth(self, index): return self.elements[index]

class Control:
    def __init__(self, name, actions, children=()): self.name=name; self.actions=actions; self.children=children
    def is_visible(self): return True
    def locator(self, selector): return Collection(self.children)
    def click(self, **kwargs): self.actions.append(self.name)

class Page:
    def __init__(self, roles): self.roles=roles
    def get_by_role(self, role, **kwargs): return Collection(self.roles.get(role, []))

class ClickBot(Bot):
    def __init__(self, page): self.page=page
    def load_helpers(self): pass

class ClickControlTests(unittest.TestCase):
    def test_menu_image_is_preferred_over_wrapping_anchor(self):
        actions=[]
        image=Control('image',actions);anchor=Control('anchor',actions,[image])
        bot=ClickBot(Page({'link':[anchor],'img':[image]}))
        bot.click(['送り状作成'])
        self.assertEqual(actions,['image'])
    def test_exact_link_with_one_unnamed_image_uses_child(self):
        actions=[]
        image=Control('image',actions);anchor=Control('anchor',actions,[image])
        ClickBot(Page({'link':[anchor]})).click(['次へ'])
        self.assertEqual(actions,['image'])
    def test_text_button_without_images_still_clicks(self):
        actions=[]
        ClickBot(Page({'button':[Control('button',actions)]})).click(['確定'])
        self.assertEqual(actions,['button'])
    def test_multiple_child_images_never_guessed(self):
        actions=[]
        root=Control('anchor',actions,[Control('a',actions),Control('b',actions)])
        with self.assertRaises(UserError): ClickBot(Page({})).click_control(root)
        self.assertEqual(actions,[])

if __name__=='__main__': unittest.main()
