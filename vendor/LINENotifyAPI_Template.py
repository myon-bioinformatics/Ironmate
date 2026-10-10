import time
import requests

token = "" #Write your Token getting by LINE Notify
url = "https://notify-api.line.me/api/notify"

def line_notify():
    payload ={"message":"LINENotifyAPI_TEST"}
    headers = {"Authorization":"Bearer"+" "+token}
    for _ in range(3):
        response = requests.post(url,data=payload, headers=headers)
        if response.status_code<300: #"response.status_code.ok" is also good
            print("successed")
        else:
            print("[HTTPError]"+str(response.status_code))
        time.sleep(1) # Sleep Time shoud be changed whatever you like
if __name__ == "__main__":
    line_notify()