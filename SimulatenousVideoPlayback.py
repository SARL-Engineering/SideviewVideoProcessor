import cv2
import tkinter as tk
from tkinter import filedialog
from time import time, sleep
import numpy as np

RESIZE_SIZE = (480, 270)
MAX_PER_ROW = 3

if __name__ == '__main__':
    tk_root = tk.Tk()
    tk_root.withdraw()

    files = filedialog.askopenfilenames(title="Video Files")
    print(files)

    video_readers = {}

    for file_path in files:
        video_readers[file_path] = cv2.VideoCapture(file_path)

    fps = video_readers[files[0]].get(cv2.CAP_PROP_FPS)

    while True:
        start_time = time()
        frames_to_show = []
        failed_reads = 0
        rows = []
        row_current_count = 0
        output_image = None
        resized = None

        for file_path in video_readers:
            return_value, current_frame = video_readers[file_path].read()

            if not return_value:
                failed_reads += 1

                if failed_reads == len(video_readers):
                    exit()
            else:
                resized = cv2.resize(current_frame, RESIZE_SIZE)

                if output_image is None:
                    output_image = resized
                else:
                    output_image = np.concatenate((output_image, resized), axis=1)

                row_current_count += 1

                if row_current_count == MAX_PER_ROW:
                    rows.append(np.copy(output_image))
                    output_image = None
                    row_current_count = 0

        black = resized.copy()
        black.fill(0)

        if output_image is not None:
            num_pad = MAX_PER_ROW - row_current_count
            for _ in range(num_pad):
                output_image = np.concatenate((output_image, black), axis=1)
            rows.append(output_image.copy())

        full_output = rows[0]
        for i in range(1, len(rows)):
            full_output = np.concatenate((full_output, rows[i]), axis=0)

        cv2.imshow("Multi-Player", full_output)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            exit()

        loop_time = time() - start_time
        desired_loop_time = (1 / fps)
        if loop_time > (1 / fps):
            print(
                "WARNING! Loop time greater than desired FPS intra-time." +
                "Playback speed will be lower than real time! desired:%f vs actual:%f" % (desired_loop_time, loop_time))

        sleep(max(0, desired_loop_time - loop_time))
