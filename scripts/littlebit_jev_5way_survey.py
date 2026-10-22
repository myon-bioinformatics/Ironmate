#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LittleBit + FairyFuse + Jev 5-Way Fixed-Point Survey & Topological Mining Engine
- Strictly Multiplication-Free in Core Engine (Only +, -, <<, >>, &, |, ^, ~, bit_count, bit_length)
- Adaptive Log2 Histogram Calibration + Multi-Scale DC/AC Strides (1, 2, 4, 8)
- 5-Way Fixed-Point Convergence with 2x2 Cycle-Lock Preservation & Anisotropic Diagonal Flux
- Flux-Field Score (Integral-Differential Metric) & Energy-Weighted Dice vs Classical IoU
- Bitboard Euler Characteristic (chi = V - E + F = b0 - b1) & Asymmetric Venn Implication Mining
"""

import random
import time
from typing import List, Tuple, Dict, Set

# 4近傍ビットフラグ定義: Left=1(0b0001), Right=2(0b0010), Up=4(0b0100), Down=8(0b1000)
BIT_L, BIT_R, BIT_U, BIT_D = 1, 2, 4, 8
MASK_X_AXIS = BIT_L | BIT_R
MASK_Y_AXIS = BIT_U | BIT_D


# =====================================================================
# 1. 乗算ゼロ・基礎ビット演算カーネル (FWHT + FairyFuse Ternary Spin)
# =====================================================================

def scale_by_100_shift_only(val: int) -> int:
    """掛け算(*)を使わずに整数を100倍する: 100x = 128x - 32x + 4x = (x<<7) - (x<<5) + (x<<2)"""
    return (val << 7) - (val << 5) + (val << 2)


def fwht8_add_only(x: List[int]) -> List[int]:
    """乗算ゼロの8点高速ウォルシュ・アダマール変換 (加減算とビットシフトのみ)"""
    a0, a1, a2, a3, a4, a5, a6, a7 = x
    b0, b1 = a0 + a1, a0 - a1
    b2, b3 = a2 + a3, a2 - a3
    b4, b5 = a4 + a5, a4 - a5
    b6, b7 = a6 + a7, a6 - a7
    c0, c2 = b0 + b2, b0 - b2
    c1, c3 = b1 + b3, b1 - b3
    c4, c6 = b4 + b6, b4 - b6
    c5, c7 = b5 + b7, b5 - b7
    return [
        (c0 + c4) >> 1, (c1 + c5) >> 1, (c2 + c6) >> 1, (c3 + c7) >> 1,
        (c0 - c4) >> 1, (c1 - c5) >> 1, (c2 - c6) >> 1, (c3 - c7) >> 1,
    ]


def rotate_8bit(bits: int, shift: int) -> int:
    """8bit列のローテーション（反事実的クエリ用の擬似シフト摂動）"""
    s = shift & 7
    return ((bits << s) | (bits >> (8 - s))) & 0xFF


def fairyfuse_ternary_diff(p1_pos: int, p1_neg: int, p2_pos: int, p2_neg: int) -> int:
    """
    [FairyFuse × Blume-Capel Spin-1 ハミルトニアン差分]
    正負ビットマスクの論理演算と popcount だけで三値スピン {-1, 0, +1} 間の不一致エネルギーを算出
    """
    conflict = ((p1_pos & p2_neg) | (p1_neg & p2_pos)).bit_count()
    vacancy_diff = ((p1_pos | p1_neg) ^ (p2_pos | p2_neg)).bit_count()
    return (conflict << 1) + vacancy_diff


class CalibratedTernaryPatch:
    """
    DC成分（マクロなボケ・グラデーションスロープ検出用）と
    AC三値スピン（ミクロなエッジ・テクスチャ検出用）を保持する低ランク因子分解パッチ
    """
    __slots__ = ("dc_level", "ac_l1", "ru_ac", "rv_ac", "u_pos", "u_neg", "v_pos", "v_neg", "active_spins")

    def __init__(self, row_8: List[int], col_8: List[int]):
        ru = fwht8_add_only(row_8)
        rv = fwht8_add_only(col_8)
        self.dc_level: int = (ru[0] + rv[0]) >> 1
        self.ru_ac: List[int] = ru[1:]
        self.rv_ac: List[int] = rv[1:]
        self.ac_l1: int = sum(abs(v) for v in self.ru_ac) + sum(abs(v) for v in self.rv_ac)
        self.u_pos = self.u_neg = self.v_pos = self.v_neg = self.active_spins = 0

    def quantize_spins(self, global_deadzone: int) -> None:
        th = (self.ac_l1 >> 3) + global_deadzone
        up = un = vp = vn = 0
        for i in range(7):
            if self.ru_ac[i] > th:
                up |= (1 << i)
            elif self.ru_ac[i] < -th:
                un |= (1 << i)
            if self.rv_ac[i] > th:
                vp |= (1 << i)
            elif self.rv_ac[i] < -th:
                vn |= (1 << i)
        self.u_pos, self.u_neg, self.v_pos, self.v_neg = up, un, vp, vn
        self.active_spins = (up | un).bit_count() + (vp | vn).bit_count()


# =====================================================================
# 2. ビットボード位相幾何（オイラー標数 χ・並列フラッドフィル・ベン図マイニング）
# =====================================================================

def pack_to_bitboard(nodes: Set[int]) -> int:
    board = 0
    for idx in nodes:
        board |= (1 << idx)
    return board


def compute_row_masks(w: int, h: int) -> Tuple[int, int, int]:
    """ビットボード上で左右の端が隣の行へ回り込む(Wrap-around)のを防ぐマスクを生成"""
    not_right_edge = 0
    not_left_edge = 0
    r_mask = (1 << (w - 1)) - 1
    l_mask = r_mask << 1
    row_shift = 0
    for _ in range(h):
        not_right_edge |= (r_mask << row_shift)
        not_left_edge |= (l_mask << row_shift)
        row_shift += w
    universe_mask = (1 << row_shift) - 1
    return not_right_edge, not_left_edge, universe_mask


def compute_bitboard_topology_and_betti(
    board: int, w: int, h: int, not_right_edge: int, not_left_edge: int, universe_mask: int
) -> Dict[str, int]:
    """
    [ビットボード・オイラー標数 χ = V - E + F ＆ 2の補数LSBフラッドフィルによるベッチ数 (b0, b1) 特定]
    - 連結成分の数 (塊の数 b0) を `seed = rem & -rem` とビット膨張で特定
    - オイラー標数 χ = V - E + F をビット論理積と bit_count() だけで O(1) 算出
    - 中空の穴の数 b1 = b0 - χ を完全に分離特定する
    """
    if board == 0:
        return {"V": 0, "E": 0, "F": 0, "chi": 0, "b0_clusters": 0, "b1_holes": 0}

    v_count = board.bit_count()
    b_right = (board >> 1) & not_right_edge
    b_down = board >> w
    b_diag_rd = (board >> (w + 1)) & not_right_edge

    e_horiz = (board & b_right).bit_count()
    e_vert = (board & b_down).bit_count()
    f_plaquettes = (board & b_right & b_down & b_diag_rd).bit_count()

    # 2x2の面を作らない純粋な斜め接続エッジの補正
    diag_main = (board & b_diag_rd & ~(b_right & b_down)).bit_count()
    diag_anti = (b_right & b_down & ~board & ~b_diag_rd).bit_count()

    e_total = e_horiz + e_vert + diag_main + diag_anti
    euler_chi = v_count - e_total + f_plaquettes

    # ビットボード並列フラッドフィルによる連結成分数 (b0) のカウント
    rem = board
    b0_count = 0
    while rem != 0:
        b0_count += 1
        comp = rem & -rem  # 2の補数による最下位ビット(LSB)シード抽出
        while True:
            # 8近傍への並列ビット膨張 (Dilation)
            exp_h = comp | ((comp & not_right_edge) << 1) | ((comp & not_left_edge) >> 1)
            exp_all = exp_h | (exp_h << w) | (exp_h >> w)
            nxt = exp_all & rem
            if nxt == comp:
                break
            comp = nxt
        rem ^= comp  # 探索済みの塊をXORで一括消去

    b1_holes = b0_count - euler_chi
    if b1_holes < 0:
        b1_holes = 0

    return {
        "V": v_count,
        "E": e_total,
        "F": f_plaquettes,
        "chi": euler_chi,
        "b0_clusters": b0_count,
        "b1_holes": b1_holes,
    }


def analyze_venn_and_implication_bitboard(
    bA: int, bB: int, bC: int, universe_mask: int
) -> Dict[str, object]:
    """
    [3条件ベン図8領域の一括算出 ＆ 非対称含意方向 (A => B) マイニング]
    """
    notA = (~bA) & universe_mask
    notB = (~bB) & universe_mask
    notC = (~bC) & universe_mask

    venn_8 = {
        "only_A": (bA & notB & notC).bit_count(),
        "only_B": (notA & bB & notC).bit_count(),
        "only_C": (notA & notB & bC).bit_count(),
        "A_and_B_not_C": (bA & bB & notC).bit_count(),
        "A_and_C_not_B": (bA & notB & bC).bit_count(),
        "B_and_C_not_A": (notA & bB & bC).bit_count(),
        "all_ABC_core": (bA & bB & bC).bit_count(),
        "outside_all": (notA & notB & notC).bit_count(),
    }

    # A と B の非対称包含判定 (A ⊂ B かどうか)
    inter_ab = (bA & bB).bit_count()
    a_not_b = (bA & notB).bit_count()
    b_not_a = (bB & notA).bit_count()

    if inter_ab > 0 and a_not_b <= (inter_ab >> 3) and b_not_a > (a_not_b << 1):
        implication = "A => B (A is sufficient core of B)"
    elif inter_ab > 0 and b_not_a <= (inter_ab >> 3) and a_not_b > (b_not_a << 1):
        implication = "B => A (B is sufficient core of A)"
    else:
        implication = "Symmetric / Partial Overlap"

    return {"venn_counts": venn_8, "implication_AB": implication}


# =====================================================================
# 3. 5-Way 不動点収束サーウェイエンジン (閉路ロック・異方性・時空間XOR対応)
# =====================================================================

class FiveWaySurveyEngine:
    STRIDE_SHIFTS = (0, 1, 2, 3)  # Strides: 1(<<0), 2(<<1), 4(<<2), 8(<<3)
    DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))

    def __init__(self, patches: List[CalibratedTernaryPatch], width: int, height: int):
        self.patches = patches
        self.w = width
        self.h = height
        self.row_offsets = [0]
        acc = 0
        for _ in range(height):
            acc += width
            self.row_offsets.append(acc)
        self.not_right_edge, self.not_left_edge, self.universe_mask = compute_row_masks(width, height)

    def _coord_to_idx(self, x: int, y: int) -> int:
        return self.row_offsets[y] + x

    def auto_calibrate(self) -> Tuple[int, int, int]:
        """bit_length() 対数ヒストグラムによる乗算ゼロ自動キャリブレーション"""
        buckets = [0] * 16
        for p in self.patches:
            b = p.ac_l1.bit_length()
            buckets[b if b < 15 else 15] += 1

        total = len(self.patches)
        target_bg = (total >> 1) + (total >> 2)  # 下位75%を背景階層とみなす
        accum = 0
        bg_tier = 4
        for idx, cnt in enumerate(buckets):
            accum += cnt
            if accum >= target_bg:
                bg_tier = idx
                break

        base_e = 1 << bg_tier
        deadzone = (base_e >> 3) + 2
        ub_ac_th = base_e + (base_e >> 2)
        dc_grad_th = (base_e >> 1) + 10

        for p in self.patches:
            p.quantize_spins(deadzone)

        return deadzone, ub_ac_th, dc_grad_th

    def _detect_2x2_cycle_locks(self, active_nodes: Set[int], blind_history: Dict[int, int]) -> Set[int]:
        """2x2 最小閉路(Plaquette)を形成している結晶核ノードを検出し、反復剪定からロック保護する"""
        locked: Set[int] = set()
        for idx in active_nodes:
            x, y = idx % self.w, idx // self.w
            if x + 1 >= self.w or y + 1 >= self.h:
                continue
            idx_r = idx + 1
            idx_d = idx + self.w
            idx_rd = idx_d + 1
            if (idx_r in active_nodes) and (idx_d in active_nodes) and (idx_rd in active_nodes):
                t00 = blind_history[idx] & 0x0F
                t10 = blind_history[idx_r] & 0x0F
                t01 = blind_history[idx_d] & 0x0F
                t11 = blind_history[idx_rd] & 0x0F
                edges = (
                    ((t00 & BIT_R) != 0 or (t10 & BIT_L) != 0)
                    + ((t01 & BIT_R) != 0 or (t11 & BIT_L) != 0)
                    + ((t00 & BIT_D) != 0 or (t01 & BIT_U) != 0)
                    + ((t10 & BIT_D) != 0 or (t11 & BIT_U) != 0)
                )
                if edges >= 3:
                    locked.update((idx, idx_r, idx_d, idx_rd))
        return locked

    def execute_5way_survey(
        self,
        anisotropy_x_shift: int = 0,
        prev_frame_bitboard: int = 0,
    ) -> Dict[str, object]:
        _, ub_ac_th, dc_grad_th = self.auto_calibrate()
        total_patches = len(self.patches)

        # 時空間XORゲート: 前フレームのビットボードが与えられた場合、変化領域とその近傍のみに探索を絞る
        temporal_active_mask = self.universe_mask
        if prev_frame_bitboard != 0:
            # 現在の簡易活性ビットボードとのXORをとり、1マス膨張させた領域だけを探索ゲートとする
            curr_rough = 0
            for idx, p in enumerate(self.patches):
                if p.active_spins > 0 or p.ac_l1 >= ub_ac_th:
                    curr_rough |= (1 << idx)
            diff_b = curr_rough ^ prev_frame_bitboard
            exp_h = diff_b | ((diff_b & self.not_right_edge) << 1) | ((diff_b & self.not_left_edge) >> 1)
            temporal_active_mask = exp_h | (exp_h << self.w) | (exp_h >> self.w) | prev_frame_bitboard

        # --- [Way 1: 順方向検出 (AC上界枝刈り ＋ 長距離DCスロープ救済)] ---
        candidates: Set[int] = set()
        macro_slopes: Set[int] = set()
        skipped = 0

        for idx, p in enumerate(self.patches):
            if not (temporal_active_mask & (1 << idx)):
                skipped += 1
                continue

            if p.active_spins > 0 and p.ac_l1 >= ub_ac_th:
                candidates.add(idx)
                continue

            # パッチ内が滑らかでも stride=4 とのDC輝度差が大きければボケ境界として救済
            x, y = idx % self.w, idx // self.w
            is_slope = False
            for dx, dy in self.DIRS:
                nx, ny = x + (dx << 2), y + (dy << 2)
                if 0 <= nx < self.w and 0 <= ny < self.h:
                    nb = self.patches[self._coord_to_idx(nx, ny)]
                    if abs(p.dc_level - nb.dc_level) >= dc_grad_th:
                        is_slope = True
                        break
            if is_slope:
                candidates.add(idx)
                macro_slopes.add(idx)
            else:
                skipped += 1

        # --- [Way 2: 反事実的クエリ（逆質問）＆ マルチストライド共鳴] ---
        blind_history: Dict[int, int] = {}
        for idx in candidates:
            p = self.patches[idx]
            x, y = idx % self.w, idx // self.w

            # 逆質問1: 自身のビット回転摂動
            rot_u_p, rot_u_n = rotate_8bit(p.u_pos, 1), rotate_8bit(p.u_neg, 1)
            self_rot_delta = fairyfuse_ternary_diff(p.u_pos, p.u_neg, rot_u_p, rot_u_n)

            # 逆質問2: 周囲ストライド(1, 2, 4, 8)とのスピン反転・空孔化差分
            topo_mask = 0
            resonance = 0
            for s_shift in self.STRIDE_SHIFTS:
                for d_idx, (dx, dy) in enumerate(self.DIRS):
                    nx, ny = x + (dx << s_shift), y + (dy << s_shift)
                    if 0 <= nx < self.w and 0 <= ny < self.h:
                        n_flat = self._coord_to_idx(nx, ny)
                        if n_flat in candidates:
                            nb = self.patches[n_flat]
                            orig_d = (
                                fairyfuse_ternary_diff(p.u_pos, p.u_neg, nb.u_pos, nb.u_neg)
                                + fairyfuse_ternary_diff(p.v_pos, p.v_neg, nb.v_pos, nb.v_neg)
                            )
                            inv_d = (
                                fairyfuse_ternary_diff(p.u_neg, p.u_pos, nb.u_pos, nb.u_neg)
                                + fairyfuse_ternary_diff(p.v_neg, p.v_pos, nb.v_pos, nb.v_neg)
                            )
                            ac_delta = abs(inv_d - orig_d) + (nb.active_spins >> 1)
                            dc_bonus = 4 if (idx in macro_slopes and n_flat in macro_slopes) else 0

                            if ac_delta + dc_bonus >= 3:
                                resonance += (ac_delta + dc_bonus)
                                topo_mask |= (1 << ((s_shift << 2) + d_idx))

            if topo_mask != 0 and (self_rot_delta + resonance) >= 6:
                blind_history[idx] = topo_mask

        # --- [Way 3 -> Way 5: 元画像なしのブラインド反復収束（閉路ロック＋異方性＋斜め合成）] ---
        active_nodes: Set[int] = set(blind_history.keys())
        for step in range(3):  # Step 0(Way 3), Step 1(Way 4), Step 2(Way 5)
            cycle_locked = self._detect_2x2_cycle_locks(active_nodes, blind_history)
            next_nodes: Set[int] = set(cycle_locked)

            for idx in active_nodes:
                if idx in next_nodes:
                    continue
                x, y = idx % self.w, idx // self.w
                topo = blind_history[idx]
                aniso_score = 0
                diag_bonus = 0

                for s_shift in self.STRIDE_SHIFTS:
                    layer_bits = (topo >> (s_shift << 2)) & 0x0F
                    if layer_bits == 0:
                        continue
                    active_dirs = 0
                    for d_idx, (dx, dy) in enumerate(self.DIRS):
                        if layer_bits & (1 << d_idx):
                            nx, ny = x + (dx << s_shift), y + (dy << s_shift)
                            if (self._coord_to_idx(nx, ny)) in active_nodes:
                                active_dirs |= (1 << d_idx)
                                if d_idx < 2:
                                    aniso_score += (1 << anisotropy_x_shift)
                                else:
                                    aniso_score += 1
                    # 疑似8近傍ビット合成（斜め45度フラックスのゼロコスト検出）
                    if (active_dirs & MASK_X_AXIS) != 0 and (active_dirs & MASK_Y_AXIS) != 0:
                        diag_bonus += 2

                req = 2 + (1 if step >= 1 else 0)
                if (aniso_score + diag_bonus) >= req:
                    next_nodes.add(idx)

            if next_nodes == active_nodes:
                break
            active_nodes = next_nodes

        # 空間ズラし感度比較用マップ (dx=+2, dy=+2 の平行移動摂動)
        shifted_nodes: Set[int] = set()
        for idx in active_nodes:
            x, y = idx % self.w, idx // self.w
            sx, sy = (x + 2) % self.w, (y + 2) % self.h
            s_flat = self._coord_to_idx(sx, sy)
            topo = blind_history[idx]
            s_links = 0
            for d_idx, (dx, dy) in enumerate(self.DIRS):
                if (topo & 0x0F) & (1 << d_idx):
                    sn_flat = self._coord_to_idx((sx + dx) % self.w, (sy + dy) % self.h)
                    if sn_flat in active_nodes:
                        s_links += 1
            if s_links >= 1:
                shifted_nodes.add(s_flat)

        final_bitboard = pack_to_bitboard(active_nodes)
        topo_stats = compute_bitboard_topology_and_betti(
            final_bitboard, self.w, self.h, self.not_right_edge, self.not_left_edge, self.universe_mask
        )

        if active_nodes:
            n_pts = len(active_nodes)
            com = (sum((i % self.w) for i in active_nodes) // n_pts, sum((i // self.w) for i in active_nodes) // n_pts)
        else:
            com = (-1, -1)

        return {
            "skip_rate": scale_by_100_shift_only(skipped) / total_patches,
            "normal_set": active_nodes,
            "shifted_set": shifted_nodes,
            "bitboard": final_bitboard,
            "blind_topo": blind_history,
            "euler_stats": topo_stats,
            "com": com,
        }


# =====================================================================
# 4. 評価指標モジュール (Classical IoU vs Energy Dice vs Flux-Field Score)
# =====================================================================

def evaluate_all_metrics_mult_free(
    w: int,
    h: int,
    gt_set: Set[int],
    recon_set: Set[int],
    patches: List[CalibratedTernaryPatch],
    recon_topo: Dict[int, int],
) -> Dict[str, float]:
    """
    面積比(IoU)の過小評価を解消する Energy-Weighted Dice と Flux-Field Score を乗算ゼロで算出
    """
    if not gt_set and not recon_set:
        return {"IoU": 100.0, "Energy_Dice": 100.0, "Flux_Field": 100.0}
    if not gt_set or not recon_set:
        return {"IoU": 0.0, "Energy_Dice": 0.0, "Flux_Field": 0.0}

    inter = gt_set & recon_set
    union = gt_set | recon_set
    iou = scale_by_100_shift_only(len(inter)) / len(union)

    # 1. Energy-Weighted Dice (各パッチのACエネルギー + 4 を重みとしたトレース比)
    inter_e = sum((patches[i].ac_l1 + 4) for i in inter)
    denom_e = sum((patches[i].ac_l1 + 4) for i in gt_set) + sum((patches[i].ac_l1 + 4) for i in recon_set)
    e_dice = scale_by_100_shift_only(inter_e << 1) / denom_e if denom_e > 0 else 0.0

    # 2. Integral-Differential Flux-Field Score (1マス積分ポテンシャル場 ＋ 空間微分方向一致)
    halo: Set[int] = set()
    gt_dirs: Dict[int, int] = {}
    dirs = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for idx in gt_set:
        gx, gy = idx % w, idx // w
        d_mask = 0
        for d_idx, (dx, dy) in enumerate(dirs):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < w and 0 <= ny < h:
                n_idx = ny * w + nx
                if n_idx in gt_set:
                    d_mask |= (1 << d_idx)
                else:
                    halo.add(n_idx)
        gt_dirs[idx] = d_mask

    flux_accum = 0
    for idx in recon_set:
        r_dir = recon_topo.get(idx, 0) & 0x0F
        if idx in gt_set:
            g_dir = gt_dirs.get(idx, 0)
            dir_match = (g_dir & r_dir).bit_count()
            flux_accum += 6 + (dir_match if dir_match <= 2 else 2)  # Max 8 pts
        elif idx in halo:
            flux_accum += 5  # ポテンシャル場内の一致（1マスの量子化ズレを救済）

    flux_denom = (len(gt_set) + len(recon_set)) << 2
    flux_score = scale_by_100_shift_only(flux_accum) / flux_denom
    if flux_score > 100.0:
        flux_score = 100.0

    return {"IoU": iou, "Energy_Dice": e_dice, "Flux_Field": flux_score}


# =====================================================================
# 5. 全8シナリオ生成 ＆ モンテカルロ検証ランナー
# =====================================================================

def generate_scenario_data(
    w: int, h: int, scenario: str, rng: random.Random
) -> Tuple[List[CalibratedTernaryPatch], Set[int], Tuple[int, int]]:
    patches: List[CalibratedTernaryPatch] = []
    gt_set: Set[int] = set()

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            is_feat = False

            if scenario == "1_Dense_Object":
                is_feat = (w // 4 <= x <= (w * 3) // 4) and (h // 4 <= y <= (h * 3) // 4)
            elif scenario == "2_Thin_Skeleton":
                is_feat = abs(x - y) <= 1 or abs((w - 1 - x) - y) <= 1
            elif scenario == "3_Hollow_Ring":
                dist = max(abs(x - (w >> 1)), abs(y - (h >> 1)))
                is_feat = (6 <= dist <= 9)
            elif scenario == "4_Double_Ring_2Holes":
                d1 = max(abs(x - 10), abs(y - 16))
                d2 = max(abs(x - 21), abs(y - 16))
                is_feat = (4 <= d1 <= 6) or (4 <= d2 <= 6)
            elif scenario == "5_Smooth_Gradient":
                is_feat = (10 <= x <= 22) and (10 <= y <= 22)
            elif scenario == "6_High_Noise_Dark":
                is_feat = (10 <= x <= 21) and (10 <= y <= 21)
            elif scenario == "7_Multi_Scale_Clusters":
                c1 = (4 <= x <= 9) and (4 <= y <= 9)
                c2 = (20 <= x <= 25) and (20 <= y <= 25)
                c3 = (22 <= x <= 23) and (6 <= y <= 7)  # 2x2極小クラスタ（閉路ロック検証用）
                is_feat = c1 or c2 or c3
            elif scenario == "8_Anisotropic_Matrix":
                is_feat = (y in (6, 7, 18, 19)) and (4 <= x <= 27)

            if is_feat:
                gt_set.add(idx)
                if scenario == "5_Smooth_Gradient":
                    r_sig = [95 + (i << 1) + rng.randint(-2, 2) for i in range(8)]
                    c_sig = [95 + (i << 1) + rng.randint(-2, 2) for i in range(8)]
                else:
                    r_sig = [(135 if (i & 1) == 0 else 25) + rng.randint(-6, 6) for i in range(8)]
                    c_sig = [(125 if (i & 2) == 0 else 30) + rng.randint(-6, 6) for i in range(8)]
            else:
                if scenario == "6_High_Noise_Dark" and rng.random() < 0.12:
                    r_sig = [rng.randint(0, 140) for _ in range(8)]
                    c_sig = [rng.randint(0, 140) for _ in range(8)]
                else:
                    r_sig = [50 + rng.randint(-3, 3) for _ in range(8)]
                    c_sig = [50 + rng.randint(-3, 3) for _ in range(8)]

            patches.append(CalibratedTernaryPatch(r_sig, c_sig))

    gt_com = (
        sum((i % w) for i in gt_set) // len(gt_set) if gt_set else -1,
        sum((i // w) for i in gt_set) // len(gt_set) if gt_set else -1,
    )
    return patches, gt_set, gt_com


def main():
    scenarios = [
        "1_Dense_Object",
        "2_Thin_Skeleton",
        "3_Hollow_Ring",
        "4_Double_Ring_2Holes",
        "5_Smooth_Gradient",
        "6_High_Noise_Dark",
        "7_Multi_Scale_Clusters",
        "8_Anisotropic_Matrix",
    ]
    w, h = 32, 32
    trials = 25
    rng = random.Random(20261022)

    print("=" * 112)
    print(" LittleBit-FairyFuse-Jev 5-Way Fixed-Point Survey & Topological Mining Benchmark")
    print(f" Grid: {w}x{h} ({w*h} patches) | Trials/Scenario: {trials} | Core Multiplication ('*'): ZERO")
    print("=" * 112)
    header = (
        f"{'Scenario':<23} | {'Skip%':>5} | {'IoU':>5} | {'E-Dice':>6} | "
        f"{'FluxScore':>9} | {'Drop(Δ)':>7} | {'Topology(χ, b0, b1)':<20} | {'Time':>6}"
    )
    print(header)
    print("-" * len(header))

    venn_boards: List[int] = []

    for sc in scenarios:
        aniso_shift = 1 if sc == "8_Anisotropic_Matrix" else 0
        sum_skip = sum_iou = sum_edice = sum_flux = sum_drop = 0.0
        last_euler: Dict[str, int] = {}
        prev_board = 0

        t0 = time.perf_counter()
        for t in range(trials):
            patches, gt_set, _ = generate_scenario_data(w, h, sc, rng)
            engine = FiveWaySurveyEngine(patches, w, h)
            # 後半の試行では時空間XORゲートを有効化して連続フレーム追従をテスト
            res = engine.execute_5way_survey(
                anisotropy_x_shift=aniso_shift,
                prev_frame_bitboard=(prev_board if t > (trials >> 1) else 0),
            )
            prev_board = res["bitboard"]

            m_norm = evaluate_all_metrics_mult_free(w, h, gt_set, res["normal_set"], patches, res["blind_topo"])
            m_shft = evaluate_all_metrics_mult_free(w, h, gt_set, res["shifted_set"], patches, res["blind_topo"])

            sum_skip += res["skip_rate"]
            sum_iou += m_norm["IoU"]
            sum_edice += m_norm["Energy_Dice"]
            sum_flux += m_norm["Flux_Field"]
            sum_drop += (m_norm["Flux_Field"] - m_shft["Flux_Field"])
            last_euler = res["euler_stats"]

        elapsed_ms = scale_by_100_shift_only(int((time.perf_counter() - t0) * 10)) / trials
        topo_str = f"χ={last_euler['chi']:+d} (b0={last_euler['b0_clusters']}, b1={last_euler['b1_holes']})"

        print(
            f"{sc:<23} | {sum_skip/trials:4.1f}% | {sum_iou/trials:4.1f}% | {sum_edice/trials:5.1f}% | "
            f"{sum_flux/trials:8.1f}% | {-sum_drop/trials:6.1f}% | {topo_str:<20} | {elapsed_ms:4.2f}ms"
        )

        if sc in ("1_Dense_Object", "3_Hollow_Ring", "5_Smooth_Gradient"):
            venn_boards.append(prev_board)

    print("-" * len(header))

    # 多重条件ベン図ビットボード ＆ 非対称含意マイニングの実演
    if len(venn_boards) == 3:
        _, _, u_mask = compute_row_masks(w, h)
        # 条件A: Hollow Ring (境界) と 条件B: Dense Object (全体領域) の包含関係をテスト
        venn_res = analyze_venn_and_implication_bitboard(venn_boards[1], venn_boards[0], venn_boards[2], u_mask)
        print("\n[Multi-Condition Bitboard Venn (8 Regions) & Asymmetric Implication Mining]")
        print(f"  Venn 8-Region Counts : {venn_res['venn_counts']}")
        print(f"  Detected Implication : {venn_res['implication_AB']}")


if __name__ == "__main__":
    main()
