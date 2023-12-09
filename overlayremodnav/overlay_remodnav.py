import pandas as pd
import numpy as np
import cv2, math, sys
from helpers.logger import logger

def overlay_video(gp: pd.DataFrame, events: pd.DataFrame, video_path: str, video_out_path: str, graph, show_graph = True, start_frame = 0, show_preview = False):
    # get total (=last) time from dataframe
    total_time = gp.iloc[-1]['t']

    # open video
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # open graph, cut edges and scale
    graph = cv2.imread(graph)
    scale_percent = 150 # percent of original size
    width = int(graph.shape[1] * scale_percent / 100)
    height = int(graph.shape[0] * scale_percent / 100)
    dim = (width, height)
    graph = cv2.resize(graph, dim)
    cut_edges = 0
    graph = graph[0:height, cut_edges:width-cut_edges*2]

    # video to be saved
    out = cv2.VideoWriter(
        video_out_path,
        cv2.VideoWriter_fourcc(*'XVID'),
        cap.get(cv2.CAP_PROP_FPS),
        (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) + graph.shape[0]))
    )

    # convert coordinates (in GP the coordinates consider 0,0 as center)
    gp['x'] = gp['x'] + 2880 # x
    gp['y'] = abs(gp['y'] - 600) # y

    # loop over each frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current_frame = start_frame
    while(cap.isOpened()): 
        key = cv2.waitKey(1) & 0xff

        # quit on Q
        if key == ord('q'):
            break

        ret, frame = cap.read()

        if(frame is None):
            break

        # compute current time (video sample rate = 25Hz)
        current_time = current_frame / 25

        # plot the GP's (gp file sample rate = 240Hz)

        # TODO: make sure that the GP's are the same as in overlay_single_participant
        start_index_of_gp = int(round(current_time / (1/240)))
        end_index_of_gp = int(round((current_time + 1/25) / (1/240)))

        gps_to_display = gp[start_index_of_gp:end_index_of_gp]

        # reset x and y
        x = -1
        y = -1

        for index, gp_sample in gps_to_display.iterrows():
            if(not math.isnan(gp_sample['x']) and not math.isnan(gp_sample['y'])):
                x = int(gp_sample['x'])
                y = int(gp_sample['y'])
                cv2.circle(frame, (x, y), 20, (255, 255, 255), -1)  

        # select all events for which: onset <= current_time <= offset
        events_to_show = events[(events['start_time'] <= current_time) & (current_time <= events['end_time'])]

        nr_events_found = events_to_show.shape[0]
        # print('found {} events'.format(nr_events_found))

        # if events are found, plot them on the screen
        if(nr_events_found > 0 and x > 0 and y > 0):
            label = events_to_show.iloc[0, events_to_show.columns.get_loc('label')]

            color = (220, 117, 0)

            if(label == 'SACC'):
                color = (72, 206, 43)
            elif(label == 'PURS'):
                color = (5, 164, 255)
            elif(label == 'LPSO'):
                color =  (242, 241, 94)
            elif(label == 'GAP'):
                color =  (40, 0, 221)

            cv2.rectangle(frame, (x + 20, y + 20), (x + 170, y + 100), color, -1, 1)
            cv2.putText(frame, label, (x + 40, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 
                1.5, (255, 255, 255), 4, cv2.LINE_AA);

        # blank frame
        new_frame = np.zeros((frame.shape[0] \
            + graph.shape[0],frame.shape[1],3), np.uint8)

        # add video
        new_frame[0:frame.shape[0], 0:frame.shape[1]] = frame

        # add graph
        if(show_graph):
            frame_width = frame.shape[1]

            # offset the graph
            # make sure the graph doesn't offset too much, the +0.15 is to account for the small space around the graph
            offset_x = int(math.floor((current_time/(total_time+0.15)) * graph.shape[1]))
            pos_x = max(0, int(frame_width/2) - offset_x)

            # graph is at max frame width, and at minimal half. otherwise, it is in between (from offset x untill end)
            graph_width = int(frame_width/2)
            if(pos_x == 0):
                graph_width = frame_width
            else:
                graph_width = int(frame_width - pos_x)

            # if we are at the max graph width (thus graph_width = frame_width), then we should shift the cropped graph
            cropped_offset_x = 0
            if(graph_width == frame_width):
                cropped_offset_x = int(offset_x - frame_width/2)

            # if we are at the end of the video (and the graph should become smaller)
            if(cropped_offset_x + graph_width > graph.shape[1]):
                graph_width = graph.shape[1] - cropped_offset_x

            # cut out the graph
            cropped = graph[
                0:graph.shape[0], # y
                cropped_offset_x:cropped_offset_x+graph_width, # x
            ]
            
            # add the graph to the frame
            new_frame[
                frame.shape[0]:frame.shape[0]+graph.shape[0], # y
                pos_x:pos_x+graph_width, # x
            ] = cropped

            # add line
            offset_line_x = int(frame_width / 2)
            padding_y = 25
            overlay = new_frame.copy()
            overlay = cv2.line(overlay, (offset_line_x, frame.shape[0] + padding_y), (offset_line_x, frame.shape[0] + graph.shape[0] - padding_y), (0, 0, 255), 3)
            alpha = 0.6
            new_frame = cv2.addWeighted(overlay, alpha, new_frame, 1 - alpha, 0)
        else:
            new_frame = frame

        # display frame
        if(show_preview):
            cv2.imshow('Frame', new_frame) 
        # cv2.moveWindow('Frame', 20, 20)

        # write frame
        logger.info('saving frame {}/{}'.format(current_frame, total_frames))
        out.write(new_frame)
        
        # increase frame number
        current_frame = current_frame + 1

    # video opslaan
    cv2.destroyAllWindows()
    cap.release()
    out.release()
    logger.success("Export stopped and video saved")

if __name__ == '__main__':
    # Load gp & events
    gp = pd.read_csv(sys.argv[1])
    events = pd.read_csv(sys.argv[2], sep='\t')
    graph = sys.argv[3]
    video = sys.argv[4]
    start_frame = int(sys.argv[5])

    overlay_video(gp, events, video, 'output.mp4', graph, True, start_frame)