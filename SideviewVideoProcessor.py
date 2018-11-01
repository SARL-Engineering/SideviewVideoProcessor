#####################################
# Imports
#####################################
# Python native imports
import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog
import os
from time import sleep, time
import multiprocessing as mp

#####################################
# Global Variables
#####################################
# Program specific
NUMBER_PROCESSING_THREADS = 4

# Assay specific
# Video looks like [start----start_light------------------------first_tap----tap---tap---tap---etc---end]
CORRECT_START_TO_FIRST_TAP_LENGTH = 27 * 60  # Seconds, so 27 minutes
SECONDS_OF_VIDEO_TO_SAVE_BEFORE_TAP = 2

RAW_FOLDER_NAME = "raw"
PROCESSED_FOLDER_NAME = "processed"
SIDEVIEW_FOLDER_NAME = "Sideview"

# Camera specific
# Note for trigger levels, if it's None, it will ignore that color entirely
CAMERA_PROFILES = {
    2: {
        "start_light_x_location": 769,
        "start_light_y_location": 167,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 658,
        "tap_light_y_location": 171,
        "tap_light_box_size": 20,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    3: {
        "start_light_x_location": 764,
        "start_light_y_location": 214,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 660,
        "tap_light_y_location": 215,
        "tap_light_box_size": 20,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    4: {
        "start_light_x_location": 747,
        "start_light_y_location": 191,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        },

        "tap_light_x_location": 628,
        "tap_light_y_location": 196,
        "tap_light_box_size": 20,

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
    def __init__(self, video_input_path, video_output_path, worker_lock):
        self.video_input_path = video_input_path
        self.video_output_path = video_output_path
        self.worker_lock = worker_lock  # type: mp.Lock

        self.filename = os.path.split(self.video_input_path)[1]

        self.fourcc = cv2.VideoWriter_fourcc(*'mp4v')

        self.camera_profile = None
        self.video_reader = None  # type: cv2.VideoCapture
        self.video_writer = None  # type: cv2.VideoWriter

        self.video_fps = None

        self.start_light_time = 0
        self.tap_light_time = 0

        self.prior_frames = []

        self.do_work()

    def do_work(self):
        self.setup_video_reader_writer()
        self.process_video()

    def setup_video_reader_writer(self):
        self.camera_profile = CAMERA_PROFILES[int(self.filename.split(" ")[CAMERA_NUMBER_POSITION_IN_SPLIT])]

        self.video_reader = cv2.VideoCapture(self.video_input_path)
        self.video_fps = self.video_reader.get(cv2.CAP_PROP_FPS)

        output_shape = (
            int(self.video_reader.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT)))

        output_path = os.path.join(self.video_output_path, self.filename)

        if not os.path.exists(output_path):
            self.video_writer = cv2.VideoWriter(output_path, self.fourcc, self.video_fps, output_shape)

    def process_video(self):
        # If output file already exists, don't reprocesses
        if not self.video_writer:
            self.locked_print("########## Skipped processing \"%s\". Output file already exists! ##########" % self.video_input_path)
            return

        self.locked_print("Started processing \"%s\"." % self.video_input_path)

        start_time = time()
        while True:
            return_value, current_frame = self.video_reader.read()

            if not return_value:
                break

            current_time = self.video_reader.get(cv2.CAP_PROP_POS_MSEC) / 1000

            # Uncomment these for preview
            # self.is_led_over_trigger_level(current_frame, self.camera_profile, "start", show_preview=True)
            # self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap", show_preview=True)

            # Watch for lights and set times accordingly
            if self.start_light_time == 0:
                if self.is_led_over_trigger_level(current_frame, self.camera_profile, "start"):
                    self.start_light_time = current_time
            elif self.tap_light_time == 0:
                self.prior_frames.append((current_time, current_frame))
                if self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap"):
                    self.tap_light_time = current_time

            # Adjust saved prior frames to only save last X seconds
            while len(self.prior_frames) > (SECONDS_OF_VIDEO_TO_SAVE_BEFORE_TAP * self.video_fps):
                del self.prior_frames[0]

            # If tap finally found, save all prev frames first
            if self.tap_light_time != 0 and len(self.prior_frames) > 0:
                for _, frame in self.prior_frames:
                    self.video_writer.write(frame)

                self.prior_frames = []

            # If we should be saving frames, do so
            is_valid_time = (current_time - self.start_light_time) < CORRECT_START_TO_FIRST_TAP_LENGTH
            if (self.start_light_time and is_valid_time) or self.tap_light_time != 0:
                self.video_writer.write(current_frame)

        if self.start_light_time == 0 or self.tap_light_time == 0:
            self.locked_print("########## FAILED processing \"%s\". Start or tap light could not be found! ##########")
        else:
            self.locked_print("Finished processing \"%s\" in %d seconds." %
                              (self.video_input_path, time() - start_time))

    def locked_print(self, string):
        self.worker_lock.acquire()
        print(string)
        self.worker_lock.release()

    @staticmethod
    def is_led_over_trigger_level(frame, camera_profile, start_or_tap, show_preview=False):
        # Variables from profile
        box_size = camera_profile["%s_light_box_size" % start_or_tap]
        box_size_half = box_size / 2

        x = camera_profile["%s_light_x_location" % start_or_tap]
        y = camera_profile["%s_light_y_location" % start_or_tap]

        x1 = int(x - box_size_half)
        x2 = int(x + box_size_half)
        y1 = int(y - box_size_half)
        y2 = int(y + box_size_half)

        red_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["red"]
        green_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["green"]
        blue_threshold = camera_profile["%s_light_trigger_levels" % start_or_tap]["blue"]

        led_area_frame = frame[y1: y2, x1: x2]

        average_color_per_row = np.average(led_area_frame, axis=0)

        # This in in (B, G, R) format
        average_color_overall = np.average(average_color_per_row, axis=0)

        if show_preview:
            cv2.imshow('frame', frame)
            cv2.imshow('%s_led_frame' % start_or_tap, led_area_frame)
            print("%s: %s" % (start_or_tap, average_color_overall))
            if cv2.waitKey(1) & 0xFF == ord('q'):
                exit()

        if blue_threshold:
            if average_color_overall[0] < blue_threshold:
                return False

        if green_threshold:
            if average_color_overall[1] < green_threshold:
                return False

        if red_threshold:
            if average_color_overall[2] < red_threshold:
                return False

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
        self.worker_lock = mp.Lock()

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
                new_process = mp.Process(target=SideviewWorker,
                                         args=(input_path, self.processed_folder_path, self.worker_lock))
                self.worker_processes[input_path] = new_process
                new_process.start()

            sleep(0.25)


if __name__ == "__main__":
    sideview_video_processor = SideviewVideoProcessor()
    sideview_video_processor.get_input_folder_path()
    sideview_video_processor.find_video_paths()
    sideview_video_processor.process_video_files()
