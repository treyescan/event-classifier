import sys
import pandas as pd

# Get arguments
participant_folder = sys.argv[1]

# Load all gaze positions
gp_path = "{}/gp.csv".format(participant_folder)
output_path = "{}/gp.tsv".format(participant_folder)

# csv to tsv
gp_df = pd.read_csv(gp_path) 
gp_df[['x', 'y']].to_csv(output_path, sep="\t", index=False, header=False)

# Show progress
print('- Converted gp.csv to gp.tsv')