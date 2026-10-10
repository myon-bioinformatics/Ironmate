import argparse
import os
import json
import requests
import time

parser = argparse.ArgumentParser()
parser.add_argument('-p',action='store_true',help='per_page: 30→100')
args = parser.parse_args()

# Initialize for API requests
# For Example: https://api.github.com/search/repositories?q=language%3APython+created%3A2020-04
years = ["2019","2020","2021"]
months = ["01","02","03","04","05","06","07","08","09","10","11","12"]
languages = ["Python","Node.js","Go"]
api = "https://api.github.com/search/repositories?q="

# Get the information of output_folder AND Make Folder, if not.
with open("input_data.json","r") as f:
    setting_data = json.load(f)
output_folder = setting_data["output_folder"]
os.makedirs(output_folder,exist_ok=True)

# Execute from API Requests to store in JSON file.
per_page_num = 30
for year in years:
    for month in months:
        for lang in languages:
            # Initialize for dump JSON file
            results_list = []
            dict_key = lang+"-"+year+"-"+month
            results_dict = {}

            # Create URL
            url = api  + "+language%3A" + lang + "+created%3A" + year + "-" + month
            if args.p:
                per_page_num=100
            url = url+"&per_page="+str(per_page_num)

            # API Request&Response, AND append to results_list
            response = requests.get(url)
            data = json.loads(response.text)
            if response.status_code < 300:
                for i in range(per_page_num):
                    full_name = data["items"][i]["full_name"] #need to add something
                    results_list.append(full_name)
            else:
                results_list.append("[HTTP_STATUS_ERROR]"+str(response.status_code)+": "+str(data["message"]))

            # Store in results_dict AND Convert to JSON Format
            results_dict[str(dict_key)]=results_list

            # Dump data to JSON file
            file_name = "./RESULTS_q="+str(url).replace(str(api),"")+".json"
            output_json_file = r"{}".format(output_folder+file_name)
            with open(output_json_file, 'a') as fp:
                json.dump(results_dict, fp, ensure_ascii=False)
                pass
            time.sleep(5)
