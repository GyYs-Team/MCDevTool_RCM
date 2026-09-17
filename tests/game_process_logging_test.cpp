#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <string>
#include <vector>

#include "game_process/logging.hpp"

namespace {
    class UniqueHandle final {
    public:
        UniqueHandle() = default;
        ~UniqueHandle() {
            reset();
        }

        UniqueHandle(const UniqueHandle&) = delete;
        UniqueHandle& operator=(const UniqueHandle&) = delete;

        HANDLE* receive() {
            reset();
            return &mHandle;
        }

        HANDLE get() const {
            return mHandle;
        }

        void reset() {
            if (mHandle != INVALID_HANDLE_VALUE) {
                CloseHandle(mHandle);
                mHandle = INVALID_HANDLE_VALUE;
            }
        }

    private:
        HANDLE mHandle = INVALID_HANDLE_VALUE;
    };

    bool writeAll(HANDLE pipe, const std::string& value) {
        DWORD written = 0;
        return WriteFile(pipe, value.data(), static_cast<DWORD>(value.size()), &written, nullptr)
            && written == value.size();
    }
}

int main() {
    UniqueHandle stdoutRead;
    UniqueHandle stdoutWrite;
    UniqueHandle stderrRead;
    UniqueHandle stderrWrite;
    if (!CreatePipe(stdoutRead.receive(), stdoutWrite.receive(), nullptr, 0)
        || !CreatePipe(stderrRead.receive(), stderrWrite.receive(), nullptr, 0)) {
        std::cerr << "Failed to create test pipes\n";
        return 1;
    }

    std::mutex mutex;
    std::condition_variable condition;
    std::vector<std::string> outputLines;
    std::vector<std::string> errorLines;
    std::atomic<bool> suppress{true};
    std::atomic<int> predicateCalls{0};
    auto suppressionPredicate = [&] {
        ++predicateCalls;
        condition.notify_all();
        return suppress.load();
    };

    mcdk::detail::PipeReaderThreads readers;
    readers.start(
        stdoutRead.get(),
        stderrRead.get(),
        true,
        [&](std::string line) {
            std::lock_guard<std::mutex> lock(mutex);
            outputLines.push_back(std::move(line));
        },
        [&](std::string line) {
            std::lock_guard<std::mutex> lock(mutex);
            errorLines.push_back(std::move(line));
        },
        suppressionPredicate
    );

    if (!writeAll(stdoutWrite.get(), "[Python] hidden output\n")
        || !writeAll(stderrWrite.get(), "[Python] hidden error\n")) {
        std::cerr << "Failed to write suppressed lines\n";
        return 1;
    }
    {
        std::unique_lock<std::mutex> lock(mutex);
        if (!condition.wait_for(lock, std::chrono::seconds(2), [&] { return predicateCalls.load() >= 2; })) {
            std::cerr << "Suppression predicate was not evaluated\n";
            return 1;
        }
    }

    suppress = false;
    if (!writeAll(stdoutWrite.get(), "[Python] visible output\n")
        || !writeAll(stderrWrite.get(), "[Python] visible error\n")) {
        std::cerr << "Failed to write visible lines\n";
        return 1;
    }
    stdoutWrite.reset();
    stderrWrite.reset();
    readers.join();

    if (outputLines != std::vector<std::string>{"[Python] visible output"}) {
        std::cerr << "Unexpected stdout lines\n";
        return 1;
    }
    if (errorLines != std::vector<std::string>{"[Python] visible error"}) {
        std::cerr << "Unexpected stderr lines\n";
        return 1;
    }
    return 0;
}
