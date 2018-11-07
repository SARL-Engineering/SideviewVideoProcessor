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
CORRECT_START_TO_FIRST_TAP_LENGTH = 30  # 27 * 60  # We need seconds, so 27 minutes * 60 #### FIXME!!!!!!
SECONDS_BETWEEN_TAPS = 20  # This is in seconds, no conversion necessary

RAW_FOLDER_NAME = "raw"
PROCESSED_FOLDER_NAME = "processed"
SIDEVIEW_FOLDER_NAME = "Sideview"

# Camera specific
# Note for trigger levels, if it's None, it will ignore that color entirely
CAMERA_PROFILES = {
    2: {
        "start_light_x_location_percentage": 0.60078125,
        "start_light_y_location_percentage": 0.2319444444,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 20,
            "green": None,
            "blue": None
        },

        "tap_light_x_location_percentage": 0.5140625,
        "tap_light_y_location_percentage": 0.2375,
        "tap_light_box_size": 20,

        "tap_light_trigger_levels": {
            "red": 20,
            "green": None,
            "blue": None
        }
    },

    3: {
        "start_light_x_location_percentage": 0.597265625,
        "start_light_y_location_percentage": 0.2979166667,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 20,
            "green": None,
            "blue": None
        },

        "tap_light_x_location_percentage": 0.515625,
        "tap_light_y_location_percentage": 0.2986111111,
        "tap_light_box_size": 20,

        "tap_light_trigger_levels": {
            "red": 15,
            "green": None,
            "blue": None
        }
    },

    4: {
        "start_light_x_location_percentage": 0.58359375,
        "start_light_y_location_percentage": 0.2659722222,
        "start_light_box_size": 20,

        "start_light_trigger_levels": {
            "red": 20,
            "green": None,
            "blue": None
        },

        "tap_light_x_location_percentage": 0.490625,
        "tap_light_y_location_percentage": 0.2722222222,
        "tap_light_box_size": 20,

        "tap_light_trigger_levels": {
            "red": 20,
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
SECONDS_BETWEEN_TAPS_HALVED = SECONDS_BETWEEN_TAPS / 2

CAMERA_NUMBER_POSITION_IN_SPLIT = 2

# Tuple positions in frame storage
VIDEO_TIME = 0
RAW_FRAME = 1


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
        self.black_frame = None

        self.start_light_time = 0
        self.tap_light_time = 0

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
        if not self.video_writer:
            self.locked_print("########## Skipped processing \"%s\". Output file already exists! ##########" % self.video_input_path)
            return

        self.locked_print("Started processing \"%s\"." % self.video_input_path)

        prior_tap_frames = []
        after_tap_frames = []

        first_tap_seen = False

        tap_light_previous = False
        tap_light_activated = False

        while True:
            return_value, current_frame = self.video_reader.read()

            if not return_value:
                break

            if self.black_frame is None:
                self.black_frame = current_frame.copy()
                self.black_frame.fill(0)

            current_time = self.video_reader.get(cv2.CAP_PROP_POS_MSEC) / 1000

            # We're at very beginning, look for start light
            if self.start_light_time == 0:
                if self.is_led_over_trigger_level(current_frame, self.camera_profile, "start"):
                    self.start_light_time = current_time
                    self.write_frames([(current_frame, current_frame)], print_writes=False)
            elif (current_time - self.start_light_time) < CORRECT_START_TO_FIRST_TAP_LENGTH:
                self.write_frames([(current_frame, current_frame)], print_writes=False)
            else:
                # Need way so that tap found only resets when value goes back UNDER the tap threshold

                # If first tap not found
                    # Look for tap and If tap found, save time and begin a local counter, add to AFTER BUFFER
                    # Otherwise, add current frame to prior buffer and clean up
                if not first_tap_seen:
                    # Building up prior buffer if we haven't found first tap yet
                    prior_tap_frames.append((current_time, current_frame))

                    while len(prior_tap_frames) > (SECONDS_BETWEEN_TAPS_HALVED * self.video_fps):
                        del prior_tap_frames[0]

                    if self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap"):
                        first_tap_seen = True
                        tap_light_previous = True
                else:
                    # Add current frame
                    after_tap_frames.append((current_time, current_frame))

                    # Check to see if we have a low to high light change
                    tap_light_currently_present = self.is_led_over_trigger_level(current_frame, self.camera_profile, "tap")

                    if tap_light_currently_present != tap_light_previous:
                        if tap_light_currently_present:
                            tap_light_activated = True

                        tap_light_previous = tap_light_currently_present

                    # We're here if the tap light has JUST changed from off to on state
                    if tap_light_activated:
                        time_between_taps = current_time - after_tap_frames[0][VIDEO_TIME]

                        # Write out all priors, would need to happen either way below
                        self.write_frames(prior_tap_frames)

                        # If no one messed up, or did in the right direction
                        if time_between_taps >= SECONDS_BETWEEN_TAPS:
                            num_frames_to_half = int(SECONDS_BETWEEN_TAPS_HALVED * self.video_fps)
                            self.write_frames(after_tap_frames[:num_frames_to_half])
                            prior_tap_frames = after_tap_frames[-num_frames_to_half:]
                        else:
                            half_of_frames = len(after_tap_frames) // 2
                            self.write_frames(after_tap_frames[:half_of_frames])

                            # Figure out missing frames and write them out
                            num_missing_frames = int((SECONDS_BETWEEN_TAPS - time_between_taps) * self.video_fps)
                            self.write_frames([(-1, self.black_frame) for _ in range(num_missing_frames)])

                            # Move remainder of frames to prior
                            prior_tap_frames = after_tap_frames[half_of_frames:]

                        tap_light_activated = False

                    # If we're here, the light hasn't just activated, we're just storing frames
                    else:
                        after_tap_frames.append((current_time, current_frame))

        # If we're here, the video is over and we need to write out all priors and enough frames to make the
        self.write_frames(prior_tap_frames)

        time_in_after_buffer = after_tap_frames[-1][VIDEO_TIME] - after_tap_frames[0][VIDEO_TIME]

        # If no one messed up, or did in the right direction
        if time_in_after_buffer >= SECONDS_BETWEEN_TAPS_HALVED:
            num_frames_to_half = int(SECONDS_BETWEEN_TAPS_HALVED * self.video_fps)
            self.write_frames(after_tap_frames[:num_frames_to_half])
        else:
            self.write_frames(after_tap_frames)

            # Figure out missing frames and write them out
            num_missing_frames = int((SECONDS_BETWEEN_TAPS_HALVED - time_in_after_buffer) * self.video_fps)
            self.write_frames([(-1, self.black_frame) for _ in range(num_missing_frames)])

    def write_frames(self, frames, print_writes=True):
        start_time = None
        end_time = None

        for frame in frames:
            if start_time is None:
                start_time = frame[VIDEO_TIME]

            self.video_writer.write(frame[RAW_FRAME])

            end_time = frame[VIDEO_TIME]

        if print_writes:
            self.locked_print("Wrote out %f to %f." % (start_time, end_time))

    def locked_print(self, string):
        self.worker_lock.acquire()
        print(string)
        self.worker_lock.release()

    @staticmethod
    def is_led_over_trigger_level(frame, camera_profile, start_or_tap, show_preview=False):
        frame_shape_y, frame_shape_x = frame.shape[:2]

        # Variables from profile
        box_size = camera_profile["%s_light_box_size" % start_or_tap]
        box_size_half = box_size / 2

        x = int(camera_profile["%s_light_x_location_percentage" % start_or_tap] * frame_shape_x)
        y = int(camera_profile["%s_light_y_location_percentage" % start_or_tap] * frame_shape_y)

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
