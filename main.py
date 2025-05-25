import json
import sys
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox
from PySide6.QtGui import (QPainter, QColor, QPen, QRadialGradient,
                           QLinearGradient, QBrush, QFont, QPainterPath)
# Added QThread, Signal for multithreading
from PySide6.QtCore import Qt, QPoint, QSize, QRectF, QThread, Signal

import requests
import random

url = "https://api.siliconflow.cn/v1/chat/completions"

headers = {
    "Authorization": "replace me",
    "Content-Type": "application/json"
}


# --- AIWorker Thread ---
class AIWorker(QThread):
    move_ready = Signal(int, int)
    error_occurred = Signal(str)

    def __init__(self, board_state, parent=None):
        super().__init__(parent)
        # Create a deep copy of the board state for thread safety
        self.board = [row[:] for row in board_state]

    def run(self):
        try:
            input_content = ""


            for r_idx in range(15):
                for c_idx in range(15):
                    input_content += str(self.board[r_idx][c_idx])
                input_content += "\n"


            input_content += "已占据位置：\n"
            for r_idx in range(15):
                for c_idx in range(15):
                    if self.board[r_idx][c_idx] != 0:
                        input_content += f"({r_idx},{c_idx}) "
                        input_content += "为" + "黑棋" if self.board[r_idx][c_idx] == 1 else "白棋"
                        input_content += "\n"

            input_content += "请你根据这个棋盘数据，给出一个合理的落子位置。你是下的白棋。最终你的落子位置设置在<luozi>行,列</luozi>，"

            payload = {
                "model": "Qwen/Qwen3-8B",
                "stream": True,
                "max_tokens": 8192,
                "enable_thinking": True,
                "thinking_budget": 2048,
                "min_p": 0.05,
                "temperature": 0.9,
                "top_p": 0.9,
                "top_k": 50,
                "frequency_penalty": 0.5,
                "n": 1,
                "stop": [],
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个AI五子棋机器人，我将输入 一个 15x15 的棋盘数据，其中没告诉的点是空的，1为黑棋，2为白棋，下标从0开始。"
                                   "请你根据这个棋盘数据，给出一个合理的落子位置。你是下的白棋。最终你的落子位置设置在<luozi>行,列</luozi>，"
                                   "便于我解析,请只输出一个结果。同时思考结果用<luozi>行,列</luozi>表示！"
                                   "你必须保证不会下在棋盘上已经有棋子的地方。"
                    },
                    {
                        "role": "user",
                        "content": input_content
                    }
                ]
            }

            output_content = ""
            response = requests.request("POST", url, json=payload, headers=headers, stream=True)

            # 处理流式响应
            for chunk in response.iter_lines():
                if chunk:
                    # 解析每个数据块
                    try:
                        chunk_text = chunk.decode('utf-8')

                        if chunk_text == "data: [DONE]":
                            break

                        # replace null with ""
                        chunk_text = chunk_text.replace("null", "\"\"")
                        chunk_text = chunk_text[5:]


                        # 转json
                        chunk_json = json.loads(chunk_text)
                        if "choices" in chunk_json:
                            if len(chunk_json["choices"]) > 0:
                                chunk_text = chunk_json["choices"][0]["delta"]["content"]
                                reason_text = chunk_json["choices"][0]["delta"]["reasoning_content"]

                                print(reason_text,end="")
                                output_content += chunk_text


                    except Exception as e:
                        print(f"解析数据块时出错: {e}")

                        # 返回一个空位
                        found_empty = []
                        for i in range(15):
                            for j in range(15):
                                if self.board[i][j] == 0:
                                    found_empty.append((i, j))

                        # 随机返回一个空位
                        if found_empty:
                            out_x, out_y = random.choice(found_empty)
                            self.move_ready.emit(out_x, out_y)


            print(output_content)

            # Parse the response
            if "<luozi>" in output_content:
                start_idx = output_content.index("<luozi>") + len("<luozi>")
                end_idx = output_content.index("</luozi>")
                position = output_content[start_idx:end_idx]
                out_x, out_y = map(int, position.split(","))

                # 判断是否有子
                if self.board[out_x][out_y] != 0:
                    # 返回一个空位
                    found_empty = []
                    for i in range(15):
                        for j in range(15):
                            if self.board[i][j] == 0:
                                found_empty.append((i, j))

                    # 随机返回一个空位
                    if found_empty:
                        out_x, out_y = random.choice(found_empty)
                        self.move_ready.emit(out_x, out_y)



                self.move_ready.emit(out_x, out_y)
            else:
                # Fallback: find the first empty spot (as per original logic)
                # print("AI返回的结果中没有落子位置") # Avoid direct print
                # 返回一个空位
                found_empty = []
                for i in range(15):
                    for j in range(15):
                        if self.board[i][j] == 0:
                            found_empty.append((i, j))

                # 随机返回一个空位
                if found_empty:
                    out_x, out_y = random.choice(found_empty)
                    self.move_ready.emit(out_x, out_y)

        except Exception as e:
            # 返回一个空位
            found_empty = []
            for i in range(15):
                for j in range(15):
                    if self.board[i][j] == 0:
                        found_empty.append((i, j))

            # 随机返回一个空位
            if found_empty:
                out_x, out_y = random.choice(found_empty)
                self.move_ready.emit(out_x, out_y)


class Gobang(QWidget):
    def __init__(self):
        super().__init__()
        self.ai_worker = None  # Attribute to hold the worker thread instance - MOVED HERE
        self.initUI()
        self.initGame()

    def initUI(self):
        self.setWindowTitle('五子棋-人机对战')
        self.setFixedSize(720, 720)
        self.grid_size = 40
        self.chess_size = 30  # Defined in original, though not directly used for drawing piece size
        self.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #D2B48C, stop:1 #8B4513);
            font-family: 'Microsoft YaHei';
        """)

    def initGame(self):
        self.board = [[0] * 15 for _ in range(15)]
        self.current_player = 1  # 1: 人类玩家(黑棋)  2: AI玩家(白棋)
        self.game_over = False
        # If a worker exists from a previous game, ensure it's cleaned up.
        if self.ai_worker:
            if self.ai_worker.isRunning():
                self.ai_worker.quit()  # Ask it to stop
                self.ai_worker.wait(500)  # Wait a bit
            self.ai_worker = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        self.drawWoodenBoard(painter)
        self.drawGridLines(painter)
        self.drawStarPoints(painter)
        self.drawChesses(painter)
        self.drawPlayerIndicator(painter)

    def drawWoodenBoard(self, painter):
        path = QPainterPath()
        path.addRoundedRect(60, 60, 600, 600, 20, 20)

        gradient = QLinearGradient(0, 0, 680, 680)
        gradient.setColorAt(0, QColor(210, 180, 140))
        gradient.setColorAt(1, QColor(139, 69, 19))

        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)

        painter.setPen(QPen(QColor(101, 67, 33), 6))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.restore()

    def drawGridLines(self, painter):
        painter.save()
        start = 80
        end = 80 + 14 * self.grid_size

        pen = QPen(QColor(101, 67, 33), 1.5, Qt.SolidLine)
        painter.setPen(pen)

        for i in range(15):
            pos = start + i * self.grid_size
            painter.drawLine(start, pos, end, pos)
            painter.drawLine(pos, start, pos, end)
        painter.restore()

    def drawStarPoints(self, painter):
        painter.save()
        start = 80
        positions = [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)]

        painter.setBrush(QColor(245, 222, 179))
        painter.setPen(Qt.NoPen)

        for x, y in positions:
            center_x = start + x * self.grid_size
            center_y = start + y * self.grid_size
            painter.drawEllipse(QPoint(center_x, center_y), 6, 6)
        painter.restore()

    def drawChesses(self, painter):
        start = 80
        for row in range(15):
            for col in range(15):
                if self.board[row][col] != 0:
                    x = start + col * self.grid_size
                    y = start + row * self.grid_size
                    self.drawChessPiece(painter, x, y, self.board[row][col])

    def drawChessPiece(self, painter, x, y, player):
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(100, 100, 100, 80))
        painter.drawEllipse(QPoint(x + 3, y + 3), 14, 14)
        painter.restore()

        painter.save()
        gradient = QRadialGradient(x - 5, y - 5, 20)
        if player == 1:
            gradient.setColorAt(0, QColor(240, 240, 240))
            gradient.setColorAt(0.7, QColor(60, 60, 60))
            gradient.setColorAt(1, QColor(30, 30, 30))
        else:
            gradient.setColorAt(0, QColor(255, 255, 255))
            gradient.setColorAt(0.7, QColor(230, 230, 230))
            gradient.setColorAt(1, QColor(210, 210, 210))

        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.setBrush(gradient)
        painter.drawEllipse(QPoint(x, y), 14, 14)

        highlight = QRadialGradient(x - 8, y - 8, 15)
        highlight.setColorAt(0, QColor(255, 255, 255, 180))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(highlight)
        painter.drawEllipse(QPoint(x, y), 8, 8)
        painter.restore()

    def drawPlayerIndicator(self, painter):
        painter.save()
        painter.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))

        pen = QPen(QColor(245, 222, 179), 2)
        painter.setPen(pen)
        player_text = "当前玩家: 人类(黑棋)" if self.current_player == 1 else "AI思考中..."
        painter.drawText(10, 30, player_text)

        indicator_x, indicator_y = 220, 10  # Adjusted original X pos slightly for text
        if self.current_player == 1:
            painter.setBrush(QColor(60, 60, 60))
        else:
            painter.setBrush(QColor(240, 240, 240))

        painter.drawEllipse(indicator_x, indicator_y, 25, 25)
        painter.restore()

    def mousePressEvent(self, event):
        if self.game_over or self.current_player != 1:
            return

        # Prevent human move if AI worker is already processing
        if self.ai_worker and self.ai_worker.isRunning():
            # Optionally, inform the user
            # QMessageBox.information(self, "提示", "AI正在思考中，请稍候。")
            return

        pos = event.position()
        start = 80
        col = round((pos.x() - start) / self.grid_size)
        row = round((pos.y() - start) / self.grid_size)

        if 0 <= row < 15 and 0 <= col < 15 and self.board[row][col] == 0:
            self.placeChess(row, col, self.current_player)
            if not self.game_over:
                self.current_player = 2
                self.trigger_ai_turn()  # Changed from robot_play

    def placeChess(self, row, col, player):
        self.board[row][col] = player
        # self.update() # Update is called after this or by player switch logic
        if self.checkWin(row, col):
            winner = "人类玩家" if player == 1 else "AI"
            self.game_over = True  # Set game_over state
            self.showGameResult(winner)  # This will also update and reset
        self.update()  # Ensure board is redrawn after piece is placed or game ends

    def trigger_ai_turn(self):
        """Initiates the AI's turn in a separate thread."""
        if self.game_over:
            return

        self.update()  # Update UI to show "AI思考中..."

        # Ensure no previous worker is still somehow referenced or running unexpectedly
        if self.ai_worker and self.ai_worker.isRunning():
            print("Warning: AI worker unexpectedly found running. Ignoring new AI turn request.")
            return

        # Pass self as parent to AIWorker so it's managed by Qt's object tree if desired,
        # though manual management of self.ai_worker is also done.
        self.ai_worker = AIWorker(self.board, self)
        self.ai_worker.move_ready.connect(self._handle_ai_move_ready)
        self.ai_worker.error_occurred.connect(self._handle_ai_error)
        # Clean up the worker object once it's finished
        self.ai_worker.finished.connect(self._ai_worker_finished)
        self.ai_worker.start()

    def _ai_worker_finished(self):
        """Slot called when AI worker thread has finished."""
        if self.ai_worker:
            self.ai_worker.deleteLater()  # Schedule the worker object for deletion
        self.ai_worker = None

    def _handle_ai_move_ready(self, row, col):
        """Slot to handle the AI's determined move."""
        if self.game_over or self.current_player != 2:  # Check if still AI's turn
            return

        if 0 <= row < 15 and 0 <= col < 15 and self.board[row][col] == 0:
            self.placeChess(row, col, self.current_player)  # current_player is 2 (AI)
            if not self.game_over:
                self.current_player = 1
        else:
            # AI returned an invalid move (e.g., occupied or out of bounds)
            # This mimics the original code's behavior of raising an error,
            # which was then caught and displayed.
            self._handle_ai_error(f"AI返回了无效/已占据位置: ({row},{col})")

        self.update()  # Ensure UI update after AI move or error handling

    def _handle_ai_error(self, error_message):
        """Slot to handle errors from the AI worker."""
        if self.game_over:  # If game ended while AI was thinking.
            return

        QMessageBox.critical(self, "AI错误", f"AI决策失败: {error_message}")
        if not self.game_over:  # Only switch player if game is not over due to this error
            self.current_player = 1  # Revert to human player's turn
        self.update()

    # Removed original robot_move and _execute_robot_move methods
    # Their logic is now in AIWorker and the _handle_ai_... slots.

    def checkWin(self, row, col):
        player = self.board[row][col]
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

        for dx, dy in directions:
            count = 1
            i, j = row + dx, col + dy
            while 0 <= i < 15 and 0 <= j < 15 and self.board[i][j] == player:
                count += 1
                i += dx
                j += dy

            i, j = row - dx, col - dy
            while 0 <= i < 15 and 0 <= j < 15 and self.board[i][j] == player:
                count += 1
                i -= dx
                j -= dy

            if count >= 5:
                return True
        return False

    def showGameResult(self, winner):
        # self.game_over is already True
        msg = QMessageBox(self)  # Parent to self for modality and style inheritance
        msg.setWindowTitle("游戏结束")
        msg.setText(f"{winner} 获胜!")
        msg.setStyleSheet("""
            QMessageBox {
                background: #D2B48C;
                font: 14px 'Microsoft YaHei';
            }
            QLabel {
                color: #8B4513;
            }
        """)
        msg.exec()
        self.initGame()  # Reset game state
        self.update()  # Refresh UI for new game

    def closeEvent(self, event):
        """Ensure AI thread is properly terminated when closing the window."""
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.quit()
            if not self.ai_worker.wait(1000):  # Wait up to 1 second
                print("AI worker did not terminate gracefully on close.")
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    game = Gobang()
    game.show()
    sys.exit(app.exec())
