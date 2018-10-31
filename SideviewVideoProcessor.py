#####################################
# Imports
#####################################
# Python native imports
import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog
import os
from time import sleep
import multiprocessing as mp

#####################################
# Global Variables
#####################################
# Program specific
NUMBER_PROCESSING_THREADS = 1

# Assay specific
# Video looks like [start----start_light------------------------first_tap----tap---tap---tap---etc---end]
CORRECT_START_TO_FIRST_TAP_LENGTH = 27 * 60  # Seconds, so 27 minutes

RAW_FOLDER_NAME = "raw"
PROCESSED_FOLDER_NAME = "processed"
SIDEVIEW_FOLDER_NAME = "Sideview"

# Camera specific
# Note for trigger levels, if it's None, it will ignore that color entirely
CAMERA_PROFILES = {
    1: {
        "start_light_x_location": 0,
        "start_light_y_location": 0,
        "start_light_box_size": 50,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 0,
        "tap_light_y_location": 0,
        "tap_light_box_size": 0,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    2: {
        "start_light_x_location": 740,
        "start_light_y_location": 140,
        "start_light_box_size": 50,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 630,
        "tap_light_y_location": 140,
        "tap_light_box_size": 50,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    3: {
        "start_light_x_location": 0,
        "start_light_y_location": 0,
        "start_light_box_size": 0,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 0,
        "tap_light_y_location": 0,
        "tap_light_box_size": 0,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    4: {
        "start_light_x_location": 0,
        "start_light_y_location": 0,
        "start_light_box_size": 0,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 0,
        "tap_light_y_location": 0,
        "tap_light_box_size": 0,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    }
}

#######################################################
#######################################################
# ##### DO NOT EDIT ANYTHING BELOW THIS POINT!!!! #####
#######################################################
#######################################################
CAMERA_NUMBER_POSITION_IN_SPLIT = 2


#####################################
# SideviewWorker Class Definition
#####################################
class SideviewWorker(object):
    def __init__(self, video_input_path, video_output_path):
        self.video_input_path = video_input_path
        self.video_output_path = video_output_path

        self.filename = os.path.split(self.video_input_path)[1]

        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        self.camera_profile = None
        self.video_reader = None  # type: cv2.VideoCapture
        self.video_writer = None  # type: cv2.VideoWriter

        self.start_light_time = 0
        self.tap_light_time = 0

        self.do_work()

    def do_work(self):
        self.setup_video_reader_writer()
        self.process_video()

    def setup_video_reader_writer(self):
        self.camera_profile = CAMERA_PROFILES[int(self.filename.split(" ")[CAMERA_NUMBER_POSITION_IN_SPLIT])]

        self.video_reader = cv2.VideoCapture(self.video_input_path)

        output_shape = (
            int(self.video_reader.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT)))

        self.video_writer = cv2.VideoWriter(os.path.join(self.video_output_path, self.filename), self.fourcc,
                                            self.video_reader.get(cv2.CAP_PROP_FPS), output_shape)

    def process_video(self):
        while True:
            return_value, current_frame = self.video_reader.read()

            if not return_value:
                break

            current_time = self.video_reader.get(cv2.CAP_PROP_POS_MSEC) / 1000
            self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap")

            if self.start_light_time == 0:
                if self.is_led_over_trigger_level(current_frame, self.camera_profile, "start"):
                    self.start_light_time = current_time
                    # print("Start: %s" % self.start_light_time)
            elif self.tap_light_time == 0:
                if self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap"):
                    self.tap_light_time = current_time
                    # print("Tap: %s\t Start-tap: %s" % (self.tap_light_time, self.tap_light_time - self.start_light_time))

            is_valid_time = (current_time - self.start_light_time) < CORRECT_START_TO_FIRST_TAP_LENGTH

            if (self.start_light_time and is_valid_time) or self.tap_light_time != 0:
                self.video_writer.write(current_frame)


    @staticmethod
    def is_led_over_trigger_level(frame, camera_profile, start_or_tap):
        # Variables from profile
        box_size = camera_profile["%s_light_box_size" % start_or_tap]
        x1 = camera_profile["%s_light_x_location" % start_or_tap]
        x2 = x1 + box_size
        y1 = camera_profile["%s_light_y_location" % start_or_tap]
        y2 = y1 + box_size

        red_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["red"]
        green_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["green"]
        blue_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["blue"]

        led_area_frame = frame[y1: y2, x1: x2]

        average_color_per_row = np.average(led_area_frame, axis=0)

        # This in in (B, G, R) format
        average_color_overall = np.average(average_color_per_row, axis=0)
        # print(average_color_overall)

        if blue_threshold:
            if average_color_overall[0] < blue_threshold:
                return False

        if green_threshold:
            if average_color_overall[1] < green_threshold:
                return False

        if red_threshold:
            if average_color_overall[2] < red_threshold:
                return False

        # cv2.imshow('frame', led_area_frame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     exit()

        return True


#####################################
# SideviewVideoProcessor Class Definition
#####################################
class SideviewVideoProcessor(object):
    def __init__(self):
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()

        self.top_folder_path = None
        self.raw_folder_path = None
        self.processed_folder_path = None

        self.paths_of_videos_to_process = []

        self.worker_processes = {}

        self.done_processing = False

    def get_input_folder_path(self):
        self.top_folder_path = filedialog.askdirectory(title="Select Input Directory")
        self.raw_folder_path = "%s/%s/%s" % (self.top_folder_path, RAW_FOLDER_NAME, SIDEVIEW_FOLDER_NAME)
        self.processed_folder_path = "%s/%s/%s" % (self.top_folder_path, PROCESSED_FOLDER_NAME, SIDEVIEW_FOLDER_NAME)

        if self.top_folder_path is None:
            print("Please enter a valid path and try again...")
            exit(2)

        if not os.path.exists(self.raw_folder_path):
            print("Raw input path \"%s\" could not be found. Please ensure directory exists. Path is case sensitive." %
                  self.raw_folder_path)
            exit(2)

        # Make output directory if doesn't exist
        if not os.path.exists(self.processed_folder_path):
            os.mkdir(self.processed_folder_path)

        print("Looking for video files in \"%s\"" % self.raw_folder_path)

    def find_video_paths(self):
        for root, directories, files in os.walk(self.raw_folder_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                self.paths_of_videos_to_process.append(file_path)

        print("Found %d files to process." % len(self.paths_of_videos_to_process))

    def process_video_files(self):
        while not self.done_processing:
            # Find any processes that are finished, join back, then delete
            to_delete = []
            for process_path in self.worker_processes:
                if not self.worker_processes[process_path].is_alive():
                    print("Finished processing \"%s\"" % process_path)
                    self.worker_processes[process_path].join()
                    to_delete.append(process_path)

            for path in to_delete:
                del self.worker_processes[path]

            # Exit if we're done
            if len(self.paths_of_videos_to_process) == 0 and len(self.worker_processes) == 0:
                print("Finished processing all files. Exiting...")
                self.done_processing = True
                break

            # Add new processes to get back up to limit
            number_of_new_processes_to_add = NUMBER_PROCESSING_THREADS - len(self.worker_processes)
            number_of_files_left_to_process = len(self.paths_of_videos_to_process)
            number_to_add = min(number_of_new_processes_to_add, number_of_files_left_to_process)

            # Only add as many as needed, or as many left
            for _ in range(number_to_add):
                input_path = self.paths_of_videos_to_process.pop()
                new_process = mp.Process(target=SideviewWorker, args=(input_path, self.processed_folder_path))
                self.worker_processes[input_path] = new_process
                new_process.start()

            sleep(0.25)


if __name__ == "__main__":
    sideview_video_processor = SideviewVideoProcessor()
    sideview_video_processor.get_input_folder_path()
    sideview_video_processor.find_video_paths()
    sideview_video_processor.process_video_files()
