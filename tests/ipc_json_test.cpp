#include <iostream>
#include <thread>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <vector>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mcdevtool/debug.h>

#pragma comment(lib, "ws2_32.lib")

static std::string makePacket(uint16_t type, const std::string& data) {
    std::string packet;
    uint32_t    len = static_cast<uint32_t>(data.size());
    packet.push_back(static_cast<char>((type >> 8) & 0xFF));
    packet.push_back(static_cast<char>(type & 0xFF));
    packet.push_back(static_cast<char>((len >> 24) & 0xFF));
    packet.push_back(static_cast<char>((len >> 16) & 0xFF));
    packet.push_back(static_cast<char>((len >> 8) & 0xFF));
    packet.push_back(static_cast<char>(len & 0xFF));
    packet += data;
    return packet;
}

static bool recvAll(SOCKET sock, char* data, int len) {
    int received = 0;
    while (received < len) {
        int n = recv(sock, data + received, len - received, 0);
        if (n <= 0) return false;
        received += n;
    }
    return true;
}

static bool sendAll(SOCKET sock, const std::string& data) {
    int sent = 0;
    while (sent < static_cast<int>(data.size())) {
        const int count = send(sock, data.data() + sent, static_cast<int>(data.size()) - sent, 0);
        if (count <= 0) return false;
        sent += count;
    }
    return true;
}

int main() {
    using namespace MCDevTool::Debug;

    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "WSAStartup failed\n";
        return 1;
    }

    DebugIPCServer server;
    std::mutex logMutex;
    std::condition_variable logCondition;
    std::vector<std::string> outputLogs;
    std::vector<std::string> errorLogs;
    server.setMessageHandler(IPC_LOG_OUTPUT_TYPE, [&](std::string line) {
        {
            std::lock_guard<std::mutex> lock(logMutex);
            outputLogs.push_back(std::move(line));
        }
        logCondition.notify_all();
    });
    server.setMessageHandler(IPC_LOG_ERROR_TYPE, [&](std::string line) {
        {
            std::lock_guard<std::mutex> lock(logMutex);
            errorLogs.push_back(std::move(line));
        }
        logCondition.notify_all();
    });
    server.start();

    std::thread clientThread([&server]() {
        SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock == INVALID_SOCKET) return;

        sockaddr_in addr{};
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(server.getPort());
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (connect(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR) {
            closesocket(sock);
            return;
        }

        const std::string outputPacket = makePacket(IPC_LOG_OUTPUT_TYPE, "[Python] client output");
        const std::string errorPacket  = makePacket(IPC_LOG_ERROR_TYPE, "[Python] client error");
        if (!sendAll(sock, outputPacket) || !sendAll(sock, errorPacket)) {
            closesocket(sock);
            return;
        }

        char header[6];
        if (!recvAll(sock, header, 6)) {
            closesocket(sock);
            return;
        }
        uint16_t type = (static_cast<unsigned char>(header[0]) << 8) | static_cast<unsigned char>(header[1]);
        uint32_t len  = (static_cast<unsigned char>(header[2]) << 24) | (static_cast<unsigned char>(header[3]) << 16)
            | (static_cast<unsigned char>(header[4]) << 8) | static_cast<unsigned char>(header[5]);
        std::string req(len, '\0');
        if (len > 0 && !recvAll(sock, req.data(), static_cast<int>(len))) {
            closesocket(sock);
            return;
        }

        if (type == IPC_JSON_REQUEST_TYPE && req.find("\"id\":") != std::string::npos) {
            std::string id = "1";
            auto        idPos = req.find("\"id\":");
            if (idPos != std::string::npos) {
                auto begin = req.find_first_of("0123456789", idPos + 5);
                auto end   = req.find_first_not_of("0123456789", begin);
                if (begin != std::string::npos) {
                    id = req.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
                }
            }
            std::string resp   = "{\"id\":" + id + ",\"ok\":true,\"result\":{\"pong\":true}}";
            std::string packet = makePacket(IPC_JSON_RESPONSE_TYPE, resp);
            sendAll(sock, packet);
        }
        closesocket(sock);
    });

    const auto connectionDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (server.getClientCount() == 0 && std::chrono::steady_clock::now() < connectionDeadline) {
        std::this_thread::yield();
    }
    if (server.getClientCount() == 0) {
        server.safeExit();
        if (clientThread.joinable()) clientThread.join();
        WSACleanup();
        std::cerr << "IPC client did not connect\n";
        return 1;
    }

    auto result = server.requestJson("ping", "{}", 10000);
    if (clientThread.joinable()) clientThread.join();
    {
        std::unique_lock<std::mutex> lock(logMutex);
        logCondition.wait_for(lock, std::chrono::seconds(2), [&] {
            return outputLogs.size() == 1 && errorLogs.size() == 1;
        });
    }
    server.safeExit();
    WSACleanup();

    if (!result.success) {
        std::cerr << "request failed: " << result.errorMessage << "\n";
        return 1;
    }
    if (outputLogs != std::vector<std::string>{"[Python] client output"}
        || errorLogs != std::vector<std::string>{"[Python] client error"}) {
        std::cerr << "IPC log packets were not routed to their handlers\n";
        return 1;
    }
    std::cout << result.responseJson << "\n";
    return result.responseJson.find("\"pong\":true") == std::string::npos ? 1 : 0;
}
