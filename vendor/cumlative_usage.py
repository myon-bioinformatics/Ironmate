import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

# Number of days
days = np.array([1, 2, 3, 4, 5, 6, 7])
# Daily usage
daily_usage = np.array([3, 3, 5, 2, 8, 4, 2])
# Cumulative usage
cumulative_usage = np.cumsum(daily_usage)

# Model for cumulative usage
def cumulative_model(t, A, k):
    return A * np.exp(k * t) - A

# Fitting
params, covariance = curve_fit(cumulative_model, days, cumulative_usage, p0=[1, 0.1])
A, k = params

print(f"A: {A}, k: {k}")

# Plotting the graph
plt.figure(figsize=(10, 6))
plt.plot(days, cumulative_usage, 'o', label='Cumulative Usage (Actual)')
plt.plot(days, cumulative_model(days, A, k), '-', label='Cumulative Usage (Model)')
plt.xlabel('Days')
plt.ylabel('Cumulative Usage (GB)')
plt.legend()
plt.title(f'Cumulative Usage Model: A={A:.2f}, k={k:.2f}')
plt.grid(True)
plt.show()
