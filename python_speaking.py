# -*- coding: utf-8 -*-
"""
Created on Tue Dec 31 17:48:41 2024
@author: hyj7904
"""

import pyttsx3
import datetime

class VoiceAssistant:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)
        self.engine.setProperty('volume', 0.9)
    
    def speak(self, text):
        print(f"助手: {text}")
        self.engine.say(text)
        self.engine.runAndWait()
    
    def greet(self):
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            self.speak("早上好！")
        elif 12 <= hour < 18:
            self.speak("下午好！")
        else:
            self.speak("晚上好！")
    
    def tell_time(self):
        time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H点%M分")
        self.speak(f"现在是{time_str}")
        
    def save(self, text, filename):
        self.engine.save_to_file(text, filename)
        self.engine.runAndWait()

def main():
    # 测试助手
    text = "2025年的最后一天，表弟还是不让告诉别人他是大番薯，等鸽说我要收房租等等更靠谱，小熊依然在CPDD"
    assistant = VoiceAssistant()
    #assistant.greet()
    #assistant.tell_time()
    assistant.speak(text)
    # assistant.save(text, "1.mp3")

if __name__ == "__main__":
    main()


