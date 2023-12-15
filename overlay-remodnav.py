import sys, re
import pandas as pd

from overlayremodnav.overlay_remodnav import overlay_video

if __name__ == '__main__':
    # Load gp & events
    gp = pd.read_csv(sys.argv[1])
    events = pd.read_csv(sys.argv[2], sep='\t')
    graph = sys.argv[3]
    video = sys.argv[4]
    start_frame = int(sys.argv[5])

    # Get participant ID for video output name
    # regex = re.findall("(P-[0-9]..)\/(T[0-9])\/([a-zA-Z0-9]*)", sys.argv[1])
    regex = re.findall("(CC[0-9]..)\/(T[0-9])\/([a-zA-Z0-9]*)", sys.argv[1])

    participant_id = regex[0][0]
    measurement_moment = regex[0][1]
    task_id = regex[0][2]

    overlay_video(gp, events, video, f'remodnav-overlay-{participant_id}.mp4', graph, True, start_frame, show_preview=True)