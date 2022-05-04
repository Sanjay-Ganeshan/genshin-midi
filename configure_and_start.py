import kivy
import kivymd

from kivymd.app import MDApp
from kivymd.uix.label import MDLabel

class MyApp(MDApp):
    def build(self):
        return MDLabel(text="hello")

def main():
    app = MyApp()
    app.run()

if __name__ == "__main__":
    main()