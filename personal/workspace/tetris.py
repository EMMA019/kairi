# 次のピースを現在のピースとしてセット
        self.new_piece()

    # ==========================================
    # ライン消去
    # ==========================================
    def clear_lines(self):
        lines_to_clear = []
        for row_idx in range(ROWS):
            if all(self.board[row_idx][col] != 0 for col in range(COLS)):
                lines_to_clear.append(row_idx)

        if lines_to_clear:
            # 消去する行を上から処理（インデックスがずれないように逆順で消す）
            for row_idx in reversed(lines_to_clear):
                del self.board[row_idx]
                self.board.insert(0, [0 for _ in range(COLS)])

            # スコア更新（消したライン数に応じて加点）
            cleared_count = len(lines_to_clear)
            if cleared_count == 1:
                self.score += 100 * self.level
            elif cleared_count == 2:
                self.score += 300 * self.level
            elif cleared_count == 3:
                self.score += 500 * self.level
            elif cleared_count == 4:
                self.score += 800 * self.level

            self.lines_cleared += cleared_count
            # 10行消すごとにレベルアップ
            self.level = 1 + self.lines_cleared // 10
            # ドロップ速度更新 (レベルが上がるほど速くなる 最小100ms)
            self.drop_speed = max(100, 800 - (self.level - 1) * 70)

            # スコア・レベルラベル更新
            self.score_label.config(text=str(self.score))
            self.level_label.config(text=str(self.level))

    # ==========================================
    # 描画関連
    # ==========================================

    # 盤面全体を再描画
    def update_board(self):
        self.canvas.delete('all')
        # 固定ブロックを描画
        for row_idx in range(ROWS):
            for col_idx in range(COLS):
                cell = self.board[row_idx][col_idx]
                if cell != 0:
                    x1 = col_idx * CELL_SIZE
                    y1 = row_idx * CELL_SIZE
                    x2 = x1 + CELL_SIZE
                    y2 = y1 + CELL_SIZE
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=COLORS[cell], outline='gray')

        # 現在操作中のピースを描画（game_overでなければ）
        if not self.game_over and hasattr(self, 'current_shape'):
            for row_idx in range(len(self.current_shape)):
                for col_idx in range(len(self.current_shape[0])):
                    if self.current_shape[row_idx][col_idx] == 1:
                        x1 = (self.piece_x + col_idx) * CELL_SIZE
                        y1 = (self.piece_y + row_idx) * CELL_SIZE
                        x2 = x1 + CELL_SIZE
                        y2 = y1 + CELL_SIZE
                        self.canvas.create_rectangle(x1, y1, x2, y2, fill=COLORS[self.current_piece_type], outline='gray')

    # ネクストピースを描画
    def draw_next_piece(self):
        self.next_canvas.delete('all')
        shape = self.next_shape
        color = COLORS[self.next_piece_type]
        for row_idx in range(len(shape)):
            for col_idx in range(len(shape[0])):
                if shape[row_idx][col_idx] == 1:
                    x1 = col_idx * CELL_SIZE
                    y1 = row_idx * CELL_SIZE
                    x2 = x1 + CELL_SIZE
                    y2 = y1 + CELL_SIZE
                    self.next_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline='gray')

    # ==========================================
    # 操作
    # ==========================================

    def move_left(self, event=None):
        if not self.game_over:
            if not self.check_collision(self.piece_x - 1, self.piece_y, self.current_shape):
                self.piece_x -= 1
                self.update_board()

    def move_right(self, event=None):
        if not self.game_over:
            if not self.check_collision(self.piece_x + 1, self.piece_y, self.current_shape):
                self.piece_x += 1
                self.update_board()

    def soft_drop(self, event=None):
        if not self.game_over:
            if not self.check_collision(self.piece_x, self.piece_y + 1, self.current_shape):
                self.piece_y += 1
                self.update_board()

    def hard_drop(self, event=None):
        if not self.game_over:
            # 真下に一気に落とす
            while not self.check_collision(self.piece_x, self.piece_y + 1, self.current_shape):
                self.piece_y += 1
            self.lock_piece()
            self.update_board()

    def rotate_piece(self, event=None):
        if not self.game_over:
            # 時計回りに90度回転（行列の転置＋各行反転）
            rotated = [list(row) for row in zip(*self.current_shape[::-1])]
            # 左端・右端にはみ出さないように調整（壁キック）
            # まず今の位置で回転できるかチェック
            if not self.check_collision(self.piece_x, self.piece_y, rotated):
                self.current_shape = rotated
            else:
                # 壁キック：左右にずらしてみる
                for offset in [1, -1, 2, -2]:
                    if not self.check_collision(self.piece_x + offset, self.piece_y, rotated):
                        self.piece_x += offset
                        self.current_shape = rotated
                        break
            self.update_board()

    # ==========================================
    # ゲームループ
    # ==========================================

    def tick(self):
        if self.game_over:
            self.canvas.create_text(
                COLS * CELL_SIZE // 2,
                ROWS * CELL_SIZE // 2,
                text="GAME OVER",
                fill='white',
                font=('Arial', 36, 'bold')
            )
            return

        # 自動落下
        if not self.check_collision(self.piece_x, self.piece_y + 1, self.current_shape):
            self.piece_y += 1
            self.update_board()
        else:
            self.lock_piece()
            self.update_board()

        # 次ティックを予約
        self.master.after(self.drop_speed, self.tick)


# ============================================================
# メインエントリポイント
# ============================================================
if __name__ == '__main__':
    root = tk.Tk()
    root.resizable(False, False)  # ウィンドウサイズ固定
    game = Tetris(root)
    root.mainloop()
