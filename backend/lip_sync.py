import librosa
import numpy as np

def generate_lip_sync_data(audio_path):
    # Load audio file
    y, sr = librosa.load(audio_path)
    
    # Calculate amplitude envelope
    frame_length = int(sr * 0.05)  # 50ms frames
    hop_length = int(sr * 0.025)   # 25ms hop
    amplitude = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    
    # Normalize and threshold for mouth open/closed
    amplitude = amplitude / np.max(amplitude)
    lip_sync_data = [{'time': i * 0.025, 'mouth_open': amp > 0.2} for i, amp in enumerate(amplitude)]
    
    return lip_sync_data
