import pandas as pd

def print_date_total_oci_from_csv(file_path):
    # Load the CSV file into a DataFrame
    dataframe = pd.read_csv(file_path)
    
    # Iterate over each row and print Date (UTC) and Total (USD)
    for index, row in dataframe.iterrows():
        print(f"Date (UTC): {row['Date (UTC)']}, Total (USD): {row['Total (USD)']}")

# Example usage
if __name__ == "__main__":  
  csv_file_path = "oci-cost-details.csv"
  print_date_total_oci_from_csv(csv_file_path)
