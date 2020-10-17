import numpy as np
import matplotlib.pyplot as plt


def mean_downscaler(data, n):
    n = int(n)
    mod = len(data) % n
    data = np.resize(data, (data.size+(n-mod)))
    if mod != 0:
        for _ in np.arange(mod):
            np.append(data, None)
    meanArr = []
    finalArr = []
    for i in data:
        meanArr.append(i)
        if len(meanArr) == n:
            finalArr.append(np.mean(meanArr))
            meanArr = []
        else:
            continue
    return finalArr
