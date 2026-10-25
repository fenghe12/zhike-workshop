"""Paper-based CogPortrait components. These are not the authors' released code.

The paper does not publish the prototype assets, FLAME conversion assets, or
the diffusion-policy likelihood estimator. They remain explicit inputs.
"""
from dataclasses import dataclass
from typing import Callable

import torch
import torch.nn as nn
import torch.nn.functional as F


CONTROL_CHANNELS = 17  # 10 AUs, four gaze coordinates, three head angles.


@dataclass
class Event:
    category: str
    start_frame: int
    end_frame: int
    amplitude: float = 1.0


class PrototypeComposer:
    """Retrieve real control sequences, resample them, and produce keypoints.

    Time interpolation and additive event composition are implementation
    choices where the manuscript does not specify the numerical algorithm.
    The caller supplies the real library and a FLAME/pupil conversion function.
    """
    def __init__(self, library: dict[str, torch.Tensor], converter: Callable):
        self.library = library
        self.converter = converter

    def __call__(self, events: list[Event], frames: int, reference):
        first = next(iter(self.library.values()))
        controls = first.new_zeros(frames, CONTROL_CHANNELS)
        for event in events:
            clip = self.library[event.category]
            if clip.ndim != 2 or clip.shape[-1] != CONTROL_CHANNELS:
                raise ValueError('A real prototype must contain T by 17 controls')
            duration = event.end_frame - event.start_frame
            if not 0 <= event.start_frame < event.end_frame <= frames:
                raise ValueError('Event interval is outside the requested sequence')
            sampled = F.interpolate(clip.T.unsqueeze(0), size=duration,
                                    mode='linear', align_corners=True)[0].T
            controls[event.start_frame:event.end_frame] += event.amplitude * sampled
        keypoints = self.converter(controls, reference)
        if keypoints.shape != (frames, 62, 2):
            raise ValueError('FLAME/pupil conversion must return T by 62 by 2 keypoints')
        return controls, keypoints


class HierarchicalPlanning:
    """Executable planning/composition/critic control flow with explicit assets.

    agent(role, payload) must return parsed structured model output. The caller
    supplies its chosen MLLM client, real prototypes, FLAME mapping, and the
    physiological rule set. This class does not pretend those assets exist.
    """
    def __init__(self, agent: Callable, library, converter: Callable,
                 physiological_checks: Callable, max_revisions=3):
        self.agent = agent
        self.composer = PrototypeComposer(library, converter)
        self.physiological_checks = physiological_checks
        self.max_revisions = max_revisions

    def __call__(self, label, reference, frames, instructions=''):
        context = dict(label=label, reference=reference, frames=frames,
                       instructions=instructions)
        planning = self.agent('planner', context)
        history = []
        for _ in range(self.max_revisions + 1):
            composition = self.agent('composer', dict(context, planning=planning,
                available_prototypes=list(self.composer.library), previous_feedback=history))
            events = [Event(**item) for item in composition['events']]
            controls, keypoints = self.composer(events, frames, reference)
            rules = self.physiological_checks(controls, keypoints)
            review = self.agent('critic', dict(context, planning=planning,
                composition=composition, physiological_results=rules))
            history.append(review)
            if review.get('approved') and rules['approved']:
                return dict(controls=controls, keypoints=keypoints, planning=planning,
                            composition=composition, reviews=history)
            if review.get('replan'):
                planning = self.agent('planner', dict(context, previous_feedback=history))
        raise RuntimeError('Planning did not satisfy semantic and physiological checks')


def tps_align(points, source_anchors, target_anchors, regularization=1e-5):
    """Fit a 2-D thin-plate spline and transform arbitrary point sequences.

    Coordinates are normalized. The small diagonal regularizer is an explicit
    numerical choice and is not specified in the paper.
    """
    n = source_anchors.shape[-2]
    def kernel(distance_squared):
        return distance_squared * torch.log(distance_squared.clamp_min(1e-8))
    delta = source_anchors.unsqueeze(-2) - source_anchors.unsqueeze(-3)
    k = kernel(delta.square().sum(-1))
    k = k + regularization * torch.eye(n, device=k.device, dtype=k.dtype)
    p = torch.cat([torch.ones_like(source_anchors[..., :1]), source_anchors], -1)
    zeros = k.new_zeros(*k.shape[:-2], 3, 3)
    system = torch.cat([torch.cat([k, p], -1),
                        torch.cat([p.transpose(-2, -1), zeros], -1)], -2)
    rhs = torch.cat([target_anchors, target_anchors.new_zeros(*target_anchors.shape[:-2], 3, 2)], -2)
    weights = torch.linalg.solve(system, rhs)
    query_delta = points.unsqueeze(-2) - source_anchors.unsqueeze(-3)
    query_k = kernel(query_delta.square().sum(-1))
    query_p = torch.cat([torch.ones_like(points[..., :1]), points], -1)
    return torch.cat([query_k, query_p], -1) @ weights


def keypoint_heatmaps(keypoints, height, width, sigma=0.02):
    """Differentiable rasterization; Gaussian width is a declared prototype choice."""
    y = torch.linspace(0, 1, height, device=keypoints.device, dtype=keypoints.dtype)
    x = torch.linspace(0, 1, width, device=keypoints.device, dtype=keypoints.dtype)
    yy, xx = torch.meshgrid(y, x, indexing='ij')
    delta_x = xx - keypoints[..., 0, None, None]
    delta_y = yy - keypoints[..., 1, None, None]
    return torch.exp(-(delta_x.square() + delta_y.square()) / (2 * sigma * sigma))


class PoseAdapter(nn.Module):
    """Wan-compatible latent pose patch projection.

    The paper says 3-D CNN without exact layer widths. This minimal choice
    matches the existing S2V 16-channel VAE and 5120-dimensional DiT tokens.
    """
    def __init__(self, latent_channels=16, token_dim=5120):
        super().__init__()
        self.proj = nn.Conv3d(latent_channels, token_dim, kernel_size=(1, 2, 2),
                              stride=(1, 2, 2))

    def forward(self, pose_latents, noisy_tokens):
        features = self.proj(pose_latents).flatten(2).transpose(1, 2)
        if features.shape != noisy_tokens.shape:
            raise ValueError('Pose tokens and noisy tokens must have the same shape')
        return noisy_tokens + features


def temporal_cfg(step, total_steps, omega_hi=8.0, omega_lo=4.0,
                 alpha=0.25, gamma=0.55):
    rho = float(step) / float(total_steps)
    if rho <= alpha:
        return omega_hi
    if rho >= gamma:
        return omega_lo
    return omega_hi + (omega_lo - omega_hi) * (rho - alpha) / (gamma - alpha)


def eye_guided_cfg(unconditional, conditional, iris_centers, step, total_steps,
                   kappa=1.0, omega_bg=1.0):
    """Fuse B,C,T,H,W predictions with the paper's dynamic eye-region CFG."""
    height, width = conditional.shape[-2:]
    center = iris_centers.mean(-2)
    distance = (iris_centers[..., 0, :] - iris_centers[..., 1, :]).square().sum(-1).sqrt()
    sigma = (kappa * distance).clamp_min(1e-4)
    y = torch.linspace(0, 1, height, device=conditional.device, dtype=conditional.dtype)
    x = torch.linspace(0, 1, width, device=conditional.device, dtype=conditional.dtype)
    yy, xx = torch.meshgrid(y, x, indexing='ij')
    squared = ((xx - center[..., 0, None, None]).square()
               + (yy - center[..., 1, None, None]).square())
    g = torch.exp(-squared / (2 * sigma[..., None, None].square()))
    omega = temporal_cfg(step, total_steps) * g + omega_bg * (1 - g)
    return unconditional + omega.unsqueeze(1) * (conditional - unconditional)


def flow_matching_loss(prediction, clean_latents, gaussian_latents):
    return F.mse_loss(prediction.float(), (clean_latents - gaussian_latents).float())


def kto_loss(policy_logp, reference_logp, desirable, reference_point,
             *, formulation, beta=625.0, desirable_weight=1.0, undesirable_weight=1.0):
    """Require real policy log-probabilities from an external likelihood estimator.

    Eq. (2) printed in the supplied PDF lacks the undesirable-label sign.
    Callers must choose its literal expression or binary-label KTO explicitly.
    Diffusion MSE is not silently substituted for a log probability.
    """
    ratio = policy_logp - reference_logp.detach()
    point = torch.as_tensor(reference_point, device=ratio.device, dtype=ratio.dtype).detach()
    label = desirable.to(torch.bool)
    if formulation == 'paper_literal':
        margin = beta * ratio - point
    elif formulation == 'binary_label':
        margin = torch.where(label, 1, -1) * (beta * ratio - point)
    else:
        raise ValueError('Select paper_literal or binary_label explicitly')
    weight = torch.where(label, desirable_weight, undesirable_weight)
    return (weight * (1 - torch.sigmoid(margin))).mean()


def joint_training_loss(prediction, clean_latents, gaussian_latents, *,
                        policy_logp, reference_logp, desirable, reference_point,
                        kto_formulation):
    fm = flow_matching_loss(prediction, clean_latents, gaussian_latents)
    preference = kto_loss(policy_logp, reference_logp, desirable, reference_point,
                          formulation=kto_formulation)
    return fm + preference, {'flow_matching': fm, 'kto': preference}
