using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Security.Cryptography;
using System.Collections.Generic;
using Microsoft.Data.Sqlite;

namespace PushFetcher
{
    class Program
    {
        static async Task Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            Console.WriteLine("==================================================");
            Console.WriteLine("    抖音推流凭证获取工具 (.NET 版 - 自动模式)     ");
            Console.WriteLine("==================================================\n");

            // 自动从 Edge 浏览器提取 Cookie
            var cookies = ExtractEdgeCookies(".douyin.com");

            if (cookies.Count == 0)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("[!] 无法从 Edge 浏览器中提取到任何 douyin.com 的 Cookie。");
                Console.ResetColor();
                Console.WriteLine("[提示] 请确保：");
                Console.WriteLine("  1. 您已在 Edge 浏览器中登录了 live.douyin.com");
                Console.WriteLine("  2. Edge 浏览器已完全关闭（否则数据库会被锁定）");
                Console.WriteLine("\n按任意键退出...");
                Console.ReadKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine($"[+] 成功从 Edge 提取到 {cookies.Count} 条 Cookie");
            Console.ResetColor();

            // 构建 CookieContainer
            var cookieContainer = new CookieContainer();
            foreach (var kv in cookies)
            {
                try
                {
                    cookieContainer.Add(new Cookie(kv.Key, kv.Value, "/", ".douyin.com"));
                }
                catch { }
            }

            // 检查关键 cookie
            if (!cookies.ContainsKey("ttwid"))
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("[!] 警告：未发现 ttwid Cookie，请确保您访问过 live.douyin.com");
                Console.ResetColor();
            }

            if (!cookies.ContainsKey("sessionid") && !cookies.ContainsKey("sessionid_ss"))
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine("[!] 警告：未发现 sessionid Cookie，可能未登录或 Cookie 已过期");
                Console.ResetColor();
            }

            var handler = new HttpClientHandler
            {
                CookieContainer = cookieContainer,
                UseCookies = true,
            };

            using var client = new HttpClient(handler);
            client.Timeout = TimeSpan.FromSeconds(20);
            client.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0");
            client.DefaultRequestHeaders.Add("Referer", "https://live.douyin.com/");

            Console.WriteLine("[*] 正在验证登录状态...");

            try
            {
                // 1. 验证登录
                string meUrl = "https://live.douyin.com/webcast/user/me/?aid=6383&device_platform=web&browser_language=zh-CN&browser_platform=Win32&browser_name=edge&browser_version=122.0.0.0";
                var meResp = await client.GetAsync(meUrl);

                if (meResp.IsSuccessStatusCode)
                {
                    var meBody = await meResp.Content.ReadAsStringAsync();
                    try
                    {
                        using var doc = JsonDocument.Parse(meBody);
                        if (doc.RootElement.GetProperty("status_code").GetInt32() == 0)
                        {
                            string nickname = "未知";
                            try { nickname = doc.RootElement.GetProperty("data").GetProperty("nickname").GetString(); } catch { }
                            Console.ForegroundColor = ConsoleColor.Green;
                            Console.WriteLine($"[+] 鉴权通过！当前主播: {nickname}");
                            Console.ResetColor();
                        }
                        else
                        {
                            Console.ForegroundColor = ConsoleColor.Yellow;
                            Console.WriteLine("[-] 鉴权失败：Cookie 可能已过期，请在 Edge 中重新登录 live.douyin.com 后再试。");
                            Console.ResetColor();
                        }
                    }
                    catch
                    {
                        Console.WriteLine("[-] 无法解析登录验证响应");
                    }
                }

                // 2. 获取推流信息
                Console.WriteLine("[*] 正在请求 RTMP 推流数据...");
                string createUrl = "https://live.douyin.com/webcast/room/web/create/?aid=6383&device_platform=web&browser_language=zh-CN&browser_platform=Win32&browser_name=edge&browser_version=122.0.0.0";
                var createResp = await client.GetAsync(createUrl);

                if (createResp.IsSuccessStatusCode)
                {
                    var createBody = await createResp.Content.ReadAsStringAsync();
                    using var doc = JsonDocument.Parse(createBody);

                    if (doc.RootElement.GetProperty("status_code").GetInt32() == 0)
                    {
                        var room = doc.RootElement.GetProperty("data").GetProperty("room");
                        var streamUrl = room.GetProperty("stream_url");

                        string pushUrl = "";
                        string pushKey = "";
                        if (streamUrl.TryGetProperty("rtmp_push_url", out var rpu)) pushUrl = rpu.GetString();
                        if (streamUrl.TryGetProperty("rtmp_key", out var rpk)) pushKey = rpk.GetString();

                        if (!string.IsNullOrEmpty(pushUrl) && !string.IsNullOrEmpty(pushKey))
                        {
                            Console.WriteLine("\n============================================================");
                            Console.ForegroundColor = ConsoleColor.Green;
                            Console.WriteLine("    ✅ 抖音推流凭证获取成功 (RTMP)");
                            Console.ResetColor();
                            Console.WriteLine("============================================================");
                            Console.ForegroundColor = ConsoleColor.Cyan;
                            Console.WriteLine($" 推流服务器 (URL): {pushUrl}");
                            Console.WriteLine($" 串流密钥 (Key)  : {pushKey}");
                            Console.ResetColor();
                            Console.WriteLine("============================================================");
                            Console.WriteLine("\n[使用建议] 请将上述信息分别填入 OBS 的对应位置。");
                        }
                        else
                        {
                            Console.ForegroundColor = ConsoleColor.Yellow;
                            Console.WriteLine("[-] 响应成功但未发现推流码。");
                            Console.ResetColor();
                            Console.WriteLine("[说明] 请先在 Edge 中打开 live.douyin.com，点击'去开播'完成初始化，然后再运行此工具。");
                            File.WriteAllText("debug_push_api.json", createBody);
                            Console.WriteLine("[*] 详细数据已保存至 debug_push_api.json 供排查。");
                        }
                    }
                    else
                    {
                        string msg = "未知错误";
                        try { msg = doc.RootElement.GetProperty("message").GetString(); } catch { }
                        Console.ForegroundColor = ConsoleColor.Red;
                        Console.WriteLine($"[-] 抖音 API 报错: {msg}");
                        Console.ResetColor();
                    }
                }
                else
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.WriteLine($"[-] 网络请求失败 HTTP {(int)createResp.StatusCode}");
                    Console.ResetColor();
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"[-] 执行过程中出现异常: {ex.Message}");
                Console.ResetColor();
            }

            Console.WriteLine("\n按回车键退出...");
            Console.ReadLine();
        }

        /// <summary>
        /// 从本地 Edge 浏览器的 SQLite 数据库中提取并解密指定域名的 Cookie
        /// </summary>
        static Dictionary<string, string> ExtractEdgeCookies(string domain)
        {
            var result = new Dictionary<string, string>();

            string userDataPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Microsoft", "Edge", "User Data");

            string localStatePath = Path.Combine(userDataPath, "Local State");
            string cookiesDbPath = Path.Combine(userDataPath, "Default", "Network", "Cookies");

            Console.WriteLine($"[DEBUG] AppData 路径: {Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)}");
            Console.WriteLine($"[DEBUG] Local State: {localStatePath} (存在: {File.Exists(localStatePath)})");
            Console.WriteLine($"[DEBUG] Cookies DB: {cookiesDbPath} (存在: {File.Exists(cookiesDbPath)})");

            if (!File.Exists(localStatePath))
            {
                Console.WriteLine("[-] 未找到 Edge 的 Local State 文件");
                return result;
            }

            if (!File.Exists(cookiesDbPath))
            {
                Console.WriteLine("[-] 未找到 Edge 的 Cookies 数据库文件");
                return result;
            }

            Console.WriteLine("[*] 正在从本地 Edge 浏览器提取 Cookie...");

            // 1. 获取解密密钥
            byte[] masterKey = GetEdgeMasterKey(localStatePath);
            if (masterKey == null)
            {
                Console.WriteLine("[-] 无法获取 Edge 解密密钥");
                return result;
            }
            Console.WriteLine($"[DEBUG] Master Key 长度: {masterKey.Length} bytes");

            // 2. 复制 Cookies 数据库到临时文件（避免锁定）
            string tempDb = Path.GetTempFileName();
            try
            {
                File.Copy(cookiesDbPath, tempDb, true);
                Console.WriteLine($"[DEBUG] Cookie DB 已复制到: {tempDb}");
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console.WriteLine($"[!] Cookie 数据库复制失败: {ex.Message}");
                Console.ResetColor();
                return result;
            }

            // 3. 从数据库读取并解密
            try
            {
                using var conn = new SqliteConnection($"Data Source={tempDb};Mode=ReadOnly");
                conn.Open();

                var cmd = conn.CreateCommand();
                cmd.CommandText = "SELECT name, encrypted_value, value FROM cookies WHERE host_key LIKE @domain";
                cmd.Parameters.AddWithValue("@domain", $"%{domain}%");

                int totalRows = 0;
                int decryptOk = 0;
                int decryptFail = 0;

                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                {
                    totalRows++;
                    string name = reader.GetString(0);
                    byte[] encryptedValue = (byte[])reader["encrypted_value"];
                    string plainValue = reader.IsDBNull(2) ? "" : reader.GetString(2);

                    if (!string.IsNullOrEmpty(plainValue))
                    {
                        result[name] = plainValue;
                        decryptOk++;
                    }
                    else if (encryptedValue != null && encryptedValue.Length > 0)
                    {
                        string decrypted = DecryptCookieValue(encryptedValue, masterKey);
                        if (!string.IsNullOrEmpty(decrypted))
                        {
                            result[name] = decrypted;
                            decryptOk++;
                        }
                        else
                        {
                            decryptFail++;
                            if (decryptFail <= 3)
                            {
                                string prefix = encryptedValue.Length >= 3 ? System.Text.Encoding.ASCII.GetString(encryptedValue, 0, 3) : "???";
                                Console.WriteLine($"[DEBUG] 解密失败 cookie: {name}, 前缀: {prefix}, 长度: {encryptedValue.Length}");
                            }
                        }
                    }
                }
                Console.WriteLine($"[DEBUG] 查询到 {totalRows} 行, 成功解密 {decryptOk}, 失败 {decryptFail}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[-] 读取 Cookie 数据库出错: {ex.Message}");
            }
            finally
            {
                try { File.Delete(tempDb); } catch { }
            }

            return result;
        }

        /// <summary>
        /// 从 Edge 的 Local State 文件中提取并解密 AES 主密钥
        /// </summary>
        static byte[] GetEdgeMasterKey(string localStatePath)
        {
            try
            {
                string json = File.ReadAllText(localStatePath);
                using var doc = JsonDocument.Parse(json);
                string encryptedKeyB64 = doc.RootElement.GetProperty("os_crypt").GetProperty("encrypted_key").GetString();
                byte[] encryptedKeyWithPrefix = Convert.FromBase64String(encryptedKeyB64);

                // 去掉 "DPAPI" 前缀 (5 bytes)
                byte[] encryptedKey = new byte[encryptedKeyWithPrefix.Length - 5];
                Array.Copy(encryptedKeyWithPrefix, 5, encryptedKey, 0, encryptedKey.Length);

                // 使用 DPAPI 解密
                byte[] masterKey = ProtectedData.Unprotect(encryptedKey, null, DataProtectionScope.CurrentUser);
                return masterKey;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[-] 解密主密钥失败: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// 使用 AES-256-GCM 解密单个 Cookie 值
        /// </summary>
        static string DecryptCookieValue(byte[] encryptedValue, byte[] masterKey)
        {
            try
            {
                // 检查前缀 "v10" 或 "v11" (3 bytes)
                if (encryptedValue.Length < 3) return null;

                string prefix = Encoding.ASCII.GetString(encryptedValue, 0, 3);
                if (prefix != "v10" && prefix != "v11") return null;

                // Nonce: 12 bytes (从 byte[3] 开始)
                byte[] nonce = new byte[12];
                Array.Copy(encryptedValue, 3, nonce, 0, 12);

                // Ciphertext + Tag: 从 byte[15] 到结尾
                // GCM tag 是最后 16 bytes
                int ciphertextLength = encryptedValue.Length - 3 - 12 - 16;
                if (ciphertextLength <= 0) return null;

                byte[] ciphertext = new byte[ciphertextLength];
                Array.Copy(encryptedValue, 15, ciphertext, 0, ciphertextLength);

                byte[] tag = new byte[16];
                Array.Copy(encryptedValue, encryptedValue.Length - 16, tag, 0, 16);

                byte[] plaintext = new byte[ciphertextLength];
                using var aes = new AesGcm(masterKey, 16);
                aes.Decrypt(nonce, ciphertext, tag, plaintext);

                return Encoding.UTF8.GetString(plaintext);
            }
            catch
            {
                return null;
            }
        }
    }
}
