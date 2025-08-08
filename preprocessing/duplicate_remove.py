import pandas as pd

# Load the two CSV files
df_base = pd.read_csv("merged_data.csv")  # Contains description_ids to be removed
df_full = pd.read_csv("All_english_descriptions.csv")  # Contains all data

# Get original row count
original_count = len(df_full)

# Remove rows where description_id is in df_base
df_filtered = df_full[~df_full['description_id'].isin(df_base['description_id']
                                                      )]

# Get new row count
new_count = len(df_filtered)

# Calculate number of removed rows
removed_count = original_count - new_count

# Output the result
print(f"Rows removed: {removed_count}")

# Save the filtered DataFrame to a new CSV
df_filtered.to_csv("filtered_file.csv", index=False)
