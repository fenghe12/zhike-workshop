"""Aligned diagnostic metrics for existing previews, without interpolating failed faces."""
from pathlib import Path
import csv,json,os,sys,subprocess
H=Path(__file__).resolve().parent
DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
OLD=H.parent/'ditalker-cogportrait-50hdtf-100steps-allzero-20261025'
sys.path.insert(0,str(DATA/'python-cpu'))
os.environ.update(TMPDIR=str(H/'tmp'),TEMP=str(H/'tmp'),TMP=str(H/'tmp'))
import cv2,numpy as np,mediapipe as mp
from PIL import Image,ImageDraw
ID='WDA_KirstenGillibrand_000_8181_8261'
raw=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(DATA/'inputs/clips'/(ID+'.mp4')),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
reference=np.frombuffer(raw,np.uint8).reshape(64,512,512,3)
LIPS=[61,146,91,181,84,17,314,405,321,375,291,409,270,269,267,0,37,39,40,185]
def landmarks(frames):
    result=[]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1,refine_landmarks=True,min_detection_confidence=.5) as mesh:
        for frame in frames:
            output=mesh.process(np.ascontiguousarray(frame))
            result.append(np.array([[p.x,p.y] for p in output.multi_face_landmarks[0].landmark]) if output.multi_face_landmarks else None)
    return result
def ssim(a,b):
    # RGB mean, 11x11 Gaussian, sigma 1.5, population covariance, valid border.
    a=a.astype(np.float64);b=b.astype(np.float64)
    f=lambda x:cv2.GaussianBlur(x,(11,11),1.5)[5:-5,5:-5]
    ma,mb=f(a),f(b);va=f(a*a)-ma*ma;vb=f(b*b)-mb*mb;cov=f(a*b)-ma*mb
    return float((((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))).mean())
ref_landmarks=landmarks(reference)
items={
 'ditalker100_cfg1':OLD/'outputs/previews/ditalker',
 'ditalker100_cfg7':OLD/'outputs/previews/ditalker-cfg7',
 'cogportrait_pose100':OLD/'outputs/previews/cogportrait',
 'ditalker220_cfg1_control':H.parent/'ditalker-cogportrait-preview220-1h-20261025/outputs/ditalker-cfg1',
 'ditalker100_native_mask':H/'outputs/di',
 'ditalker_initialzero_native_mask':H/'outputs/di',
}
summary={}
for label,folder in items.items():
    filename={'ditalker100_native_mask':'strict100-native-mask.frames.npy','ditalker_initialzero_native_mask':'initialzero-native-mask.frames.npy'}.get(label,'generated.frames.npy')
    array=np.load(folder/filename,allow_pickle=False)
    indices=np.arange(64)[::4] if label.startswith('ditalker') else np.arange(64)
    assert array.shape==reference[indices].shape
    detected=landmarks(array);rows=[]
    for i,(prediction,index) in enumerate(zip(array,indices)):
        target=reference[index];difference=prediction.astype(np.float64)-target
        mse=float(np.square(difference).mean())
        rec=dict(frame=i,source_frame=int(index),mae=float(np.abs(difference).mean()),mse=mse,psnr_db=float(10*np.log10(255**2/mse)) if mse else None,ssim_rgb=ssim(prediction,target),generated_face_detected=detected[i] is not None,reference_face_detected=ref_landmarks[index] is not None,spatial_std=float(prediction.astype(float).std(axis=(0,1)).mean()))
        if detected[i] is not None and ref_landmarks[index] is not None:
            a=ref_landmarks[index];b=detected[i]
            eye_left=(a[33]+a[133])/2;eye_right=(a[263]+a[362])/2;distance=np.linalg.norm(eye_left-eye_right)
            rec['facemesh468_normalized_mean_distance']=float(np.linalg.norm(a[:468]-b[:468],axis=-1).mean()/distance)
            rec['mouth20_normalized_mean_distance']=float(np.linalg.norm(a[LIPS]-b[LIPS],axis=-1).mean()/distance)
        rows.append(rec)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (H/'outputs'/(label+'-frame-metrics.csv')).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    metric_names=['mae','mse','psnr_db','ssim_rgb','spatial_std','facemesh468_normalized_mean_distance','mouth20_normalized_mean_distance']
    summary[label]=dict(source_sample=ID,split='training',frames=len(array),source_indices=indices.tolist(),face_detection_coverage=sum(p is not None for p in detected)/len(array),face_detection_count=sum(p is not None for p in detected),reference_detection_count=sum(ref_landmarks[j] is not None for j in indices),**{k:float(np.mean([r[k] for r in rows if k in r and r[k] is not None])) if any(k in r and r[k] is not None for r in rows) else None for k in metric_names})
    np.savez_compressed(H/'outputs'/(label+'-landmarks.npz'),points=np.stack([p if p is not None else np.full((478,2),np.nan) for p in detected]),detected=np.array([p is not None for p in detected]))
    print(json.dumps(dict(variant=label,**summary[label])),flush=True)
summary['protocol']=dict(resolution=[512,512],ssim='RGB mean; Gaussian 11x11 sigma1.5; population covariance; range255; valid border',landmark_metric='Mean 2D distance normalized by reference interocular distance; no spatial alignment; paired detected frames only; MediaPipe refined FaceMesh confidence0.5',missing_face_policy='No interpolation; absent facial metrics are null, coverage is explicit',not_syncnet_lse_d=True,reference_resize='ffmpeg center square crop and scale512',limitations=['One training-set identity; no held-out generalization estimate.','The methods have different frame rates and frame counts; no direct ranking.','PSNR/SSIM compare individual generated frames with the paired source, not perceptual equivalence or audio synchronization.'])
(H/'outputs/quality-metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
