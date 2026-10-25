"""Real HDTF facial landmarks, upper-face controls and Deep3D alignment points."""
import json,os,time
from pathlib import Path
import cv2,numpy as np
import mediapipe as mp
H=Path(__file__).resolve().parent
os.environ.update(TMPDIR=str(H/'tmp'),TEMP=str(H/'tmp'),TMP=str(H/'tmp'))
# 16 eyelid contour points per eye, ten brow points per eye, ten iris points.
LEFT=[33,7,163,144,145,153,154,155,133,173,157,158,159,160,161,246]
RIGHT=[263,249,390,373,374,380,381,382,362,398,384,385,386,387,388,466]
BROWS=[70,63,105,66,107,46,53,52,65,55,300,293,334,296,336,276,283,282,295,285]
EYES=LEFT+RIGHT+BROWS+list(range(468,478))
assert len(EYES)==62
# Five points in standard Deep3DFaceRecon order: eyes, nose, mouth corners.
FIVE=[33,263,1,61,291]
mesh=mp.solutions.face_mesh.FaceMesh(static_image_mode=False,max_num_faces=1,refine_landmarks=True,min_detection_confidence=.5,min_tracking_confidence=.5)
manifest=json.loads((H/'inputs/training-manifest.json').read_text())
records=[]
for i,row in enumerate(manifest):
    out=H/'inputs/features'/(row['id']+'.npz')
    if out.exists():
        records.append(dict(id=row['id'],cached=True));continue
    cap=cv2.VideoCapture(str(H/row['file']))
    assert cap.isOpened(),row['id']
    fps=cap.get(cv2.CAP_PROP_FPS)
    points=[]; detected=[]
    for frame in range(64):
        ok,img=cap.read();assert ok,(row['id'],frame)
        ih,iw=img.shape[:2]
        side=min(ih,iw);y=(ih-side)//2;x=(iw-side)//2
        img=cv2.resize(img[y:y+side,x:x+side],(512,512))
        result=mesh.process(cv2.cvtColor(img,cv2.COLOR_BGR2RGB))
        if result.multi_face_landmarks:
            lm=np.asarray([[v.x,v.y,v.z] for v in result.multi_face_landmarks[0].landmark],dtype=np.float32)
            points.append(lm);detected.append(frame)
        else:points.append(None)
    cap.release()
    if len(detected)<48:raise RuntimeError(f"Insufficient face detection: {row['id']} {len(detected)}/64")
    # Interpolate only failed detections between observed real frames.
    known=np.stack([points[j] for j in detected]);arr=np.empty((64,478,3),dtype=np.float32)
    for p in range(478):
        for c in range(3):arr[:,p,c]=np.interp(np.arange(64),detected,known[:,p,c])
    five=arr[:,FIVE,:2].copy()*512
    # Eye centers are the average of both eye corners.
    five[:,0]=(arr[:,33,:2]+arr[:,133,:2])*256
    five[:,1]=(arr[:,263,:2]+arr[:,362,:2])*256
    np.savez_compressed(out,landmarks=arr,eye62=arr[:,EYES,:2],five_points=five,fps=np.asarray(fps),detected_frames=np.asarray(detected))
    rec=dict(id=row['id'],detected_frames=len(detected),source_fps=fps,frames=64,resolution=[512,512],eye_points=62)
    records.append(rec);print(json.dumps(dict(completed=i+1,total=50,**rec)),flush=True)
(H/'outputs/facial-extraction.json').write_text(json.dumps(dict(samples=records,keypoint_source='MediaPipe refined FaceMesh measured from genuine HDTF videos',eye62_indices=EYES,failed_detection_policy='linear interpolation between observed detections'),indent=2)+'\n')
