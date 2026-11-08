import Foundation
import SQLite3

/// Minimal SQLite wrapper. The lexicon ships inside the app bundle and is
/// opened as immutable (no journal or locking); the reader's library of texts
/// lives in Application Support and is read normally, and written by
/// ModuleManager on its own connection.
final class SQLiteDatabase {
    enum Mode { case immutable, readOnly, readWrite }

    enum Failure: Error, CustomStringConvertible {
        case open(String), prepare(String)
        var description: String {
            switch self {
            case .open(let m): return "Could not open database: \(m)"
            case .prepare(let m): return "SQL error: \(m)"
            }
        }
    }

    private var handle: OpaquePointer?

    init(url: URL, mode: Mode = .immutable) throws {
        // file:///…?immutable=1 — absoluteString is already percent-encoded.
        let uri = url.absoluteString + (mode == .immutable ? "?immutable=1" : "")
        let flags: Int32
        switch mode {
        case .immutable, .readOnly: flags = SQLITE_OPEN_READONLY | SQLITE_OPEN_URI | SQLITE_OPEN_NOMUTEX
        case .readWrite: flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_URI | SQLITE_OPEN_FULLMUTEX
        }
        if sqlite3_open_v2(uri, &handle, flags, nil) != SQLITE_OK {
            let message = handle.map { String(cString: sqlite3_errmsg($0)) } ?? "unknown error"
            sqlite3_close(handle)
            handle = nil
            throw Failure.open(message)
        }
        if mode != .immutable { sqlite3_busy_timeout(handle, 5000) }   // the library may be being written
    }

    deinit { sqlite3_close(handle) }

    /// SQLite's message, with the extended code (e.g. 14 = can't open, 266 = short read).
    private var errorMessage: String {
        "\(String(cString: sqlite3_errmsg(handle))) (\(sqlite3_extended_errcode(handle)))"
    }

    /// Runs a statement that returns no rows (or whose rows don't matter).
    func execute(_ sql: String, _ args: [Any?] = []) throws {
        try query(sql, args) { _ in }
    }

    /// Runs several statements with no arguments (BEGIN, PRAGMA …).
    func executeScript(_ sql: String) throws {
        if sqlite3_exec(handle, sql, nil, nil, nil) != SQLITE_OK {
            throw Failure.prepare(errorMessage)
        }
    }

    /// The first column of the first row, as a string.
    func string(_ sql: String, _ args: [Any?] = []) throws -> String? {
        var out: String?
        try query(sql, args) { r in if out == nil { out = r.string(0) } }
        return out
    }

    /// Runs `sql` with positional `args` (Int, String, or nil) and calls `row` for each result row.
    func query(_ sql: String, _ args: [Any?] = [], row: (SQLiteRow) -> Void) throws {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &stmt, nil) == SQLITE_OK, let stmt else {
            throw Failure.prepare(errorMessage)
        }
        defer { sqlite3_finalize(stmt) }
        for (i, arg) in args.enumerated() {
            let index = Int32(i + 1)
            switch arg {
            case let v as Int: sqlite3_bind_int64(stmt, index, Int64(v))
            case let v as String: sqlite3_bind_text(stmt, index, v, -1, SQLITE_TRANSIENT)
            default: sqlite3_bind_null(stmt, index)
            }
        }
        var rc = sqlite3_step(stmt)
        while rc == SQLITE_ROW {
            row(SQLiteRow(stmt: stmt))
            rc = sqlite3_step(stmt)
        }
        if rc != SQLITE_DONE {
            throw Failure.prepare(errorMessage)
        }
    }
}

struct SQLiteRow {
    fileprivate let stmt: OpaquePointer

    func int(_ column: Int32) -> Int { Int(sqlite3_column_int64(stmt, column)) }

    func optionalInt(_ column: Int32) -> Int? {
        sqlite3_column_type(stmt, column) == SQLITE_NULL ? nil : int(column)
    }

    func string(_ column: Int32) -> String? {
        guard let c = sqlite3_column_text(stmt, column) else { return nil }
        return String(cString: c)
    }

    func data(_ column: Int32) -> Data? {
        guard let bytes = sqlite3_column_blob(stmt, column) else { return nil }
        return Data(bytes: bytes, count: Int(sqlite3_column_bytes(stmt, column)))
    }
}

/// SQLite's "copy this string now" destructor sentinel, which Swift can't import directly.
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
