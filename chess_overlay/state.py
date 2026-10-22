"""Keep a chess.Board in sync with the recognised placement using legal moves."""
import chess

from .recognize import UNKNOWN


def matches(board, placement, max_unknown=12):
    unknown = 0
    for sq, p in placement.items():
        if p == UNKNOWN:
            unknown += 1
            continue
        if board.piece_at(sq) != p:
            return False
    return unknown <= max_unknown


class GameTracker:
    def __init__(self):
        self.board = chess.Board()
        self.uncertain = True

    def reset(self):
        self.board = chess.Board()
        self.uncertain = False

    def update(self, placement, prefer_turn=None):
        """Advance the internal board to agree with `placement`. Returns True if it changed."""
        b = self.board
        if matches(b, placement):
            return False
        for mv in b.legal_moves:
            b.push(mv)
            if matches(b, placement):
                self.uncertain = False
                return True
            b.pop()
        for mv in list(b.legal_moves):
            b.push(mv)
            for mv2 in list(b.legal_moves):
                b.push(mv2)
                if matches(b, placement):
                    self.uncertain = False
                    return True
                b.pop()
            b.pop()
        if matches(chess.Board(), placement):
            self.reset()
            return True
        self._rebuild(placement, prefer_turn)
        return True

    def _rebuild(self, placement, prefer_turn):
        nb = chess.Board(None)
        for sq, p in placement.items():
            if p not in (None, UNKNOWN):
                nb.set_piece_at(sq, p)
        rights = ""
        if nb.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE):
            if nb.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
                rights += "K"
            if nb.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
                rights += "Q"
        if nb.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK):
            if nb.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
                rights += "k"
            if nb.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
                rights += "q"
        nb.set_castling_fen(rights or "-")
        turns = [prefer_turn] if prefer_turn is not None else []
        turns += [t for t in (chess.WHITE, chess.BLACK) if t not in turns]
        for t in turns:
            nb.turn = t
            if nb.is_valid():
                break
        self.board = nb
        self.uncertain = True
