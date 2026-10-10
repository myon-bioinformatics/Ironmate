import PySimpleGUI as sg
import glob
import os
from PIL import Image

#initialize GUI
sg.theme("TealMono")
layout = [
            [sg.Text("This tool is used to Convert image files(.png,.ipg,.jpeg,.gif,.svg) to webp files)")],
            [sg.Text("Image File: "), sg.InputText(), sg.FileBrowse(key="img_file")],
            [sg.Text("Image Folder: "),sg.InputText(), sg.FolderBrowse(key="img_folder")],
            [sg.Text('Convert image files to webp files in Image Folder: '), sg.Checkbox('agree',key="agree")],
            [sg.Submit("File Submit",key="file_submit"),sg.Submit("Folder Submit",key="folder_submit")],
            [sg.Text('Progress Bar: '),sg.ProgressBar(max_value=1,orientation="h",size=(20,20),key="prog_bar")],
            [sg.Text('Status'),sg.Output(key='status',size=(10,1))],
            [sg.Text('Results'),sg.Output(key='results',size=(20,1))],
        ]
window = sg.Window(title='Convert to webp files', layout=layout)

# confirm img files(.png,.ipg,.jpeg,.gif,.svg) in Image Folder AND make Lists
def confirm_files(img_folder):
    img_file_list = []
    for f in glob.glob(r'{}/*.*'.format(img_folder)): #LIST
        if os.path.splitext(f)[1] in (".jpg", ".png", ".jpeg",".gif",".svg"):
            img_file_list.append(f)
            window['status'].update("Confirmed!!")
    return img_file_list #LIST

# convert img file to .webp file
def convert_file(img_file):
    w = r"{}".format(os.path.splitext(img_file)[0]) #filename without extension
    webp_img = r"{}".format(w+".webp")
    with Image.open(img_file) as i:
        i.save(webp_img,quality=50,format="webp",optimize=True)

# GUI Operate
while True:
    event, values = window.read()

    #[Execute]: Click "x Button" on upper right
    if event == sg.WIN_CLOSED:
        break

    #[Execute]: sg.FolderBrowse(key="img_folder"), sg.Checkbox('agree',key="agree") and sg.Submit("Folder Submit",key="folder_submit")
    if event =="folder_submit" and values["img_folder"] and values["agree"]:
        img_file_list  = confirm_files(values["img_folder"]) #LIST
        window["prog_bar"].update(max = len(img_file_list ),current_count = 0)
        for idx,img in enumerate(img_file_list ,start = 1):
            convert_file(img)
            window["prog_bar"].update(current_count=idx)
        window['results'].update("All Completed!")
        window['status'].update("")

    #[Execute]: sg.FileBrowse(key="img_file"),sg.Submit("File Submit",key="file_submit"),
    if event == "file_submit" and values["img_file"]:
        window["prog_bar"].update(max = 1,current_count = 0)
        convert_file(values["img_file"])
        window["prog_bar"].update(current_count = 1)
        window['results'].update("Completed!")
        window['status'].update("")
window.close()