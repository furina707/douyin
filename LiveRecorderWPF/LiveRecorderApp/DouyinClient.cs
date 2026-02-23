using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Linq;

namespace LiveRecorderApp
{
    public class DouyinClient
    {
        private readonly HttpClient _httpClient;

        public DouyinClient()
        {
            var handler = new HttpClientHandler { UseCookies = true };
            _httpClient = new HttpClient(handler);
            
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36");
            _httpClient.DefaultRequestHeaders.Add("Referer", "https://live.douyin.com/");
            _httpClient.DefaultRequestHeaders.Add("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8");
            _httpClient.DefaultRequestHeaders.Add("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8");
            _httpClient.DefaultRequestHeaders.Add("Sec-Ch-Ua", "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"");
            _httpClient.DefaultRequestHeaders.Add("Sec-Ch-Ua-Mobile", "?0");
            _httpClient.DefaultRequestHeaders.Add("Sec-Ch-Ua-Platform", "\"Windows\"");
            _httpClient.DefaultRequestHeaders.Add("Sec-Fetch-Dest", "document");
            _httpClient.DefaultRequestHeaders.Add("Sec-Fetch-Mode", "navigate");
            _httpClient.DefaultRequestHeaders.Add("Sec-Fetch-Site", "same-origin");
            _httpClient.DefaultRequestHeaders.Add("Sec-Fetch-User", "?1");
            _httpClient.DefaultRequestHeaders.Add("Upgrade-Insecure-Requests", "1");
        }

        public async Task<(bool IsLive, string StreamUrl, string Title, string Nickname)> GetStatusAsync(string roomId)
        {
            try
            {
                // Ensure ttwid
                if (System.IO.File.Exists(@"..\..\cookie_ttwid.txt"))
                {
                    string ttwid = System.IO.File.ReadAllText(@"..\..\cookie_ttwid.txt").Trim();
                    if (!string.IsNullOrEmpty(ttwid))
                    {
                        var cookieContainer = new System.Net.CookieContainer();
                        cookieContainer.Add(new System.Net.Cookie("ttwid", ttwid, "/", ".douyin.com"));
                    }
                }
                await _httpClient.GetAsync("https://www.douyin.com/");
                await _httpClient.GetAsync("https://live.douyin.com/");
                
                string apiUrl = $"https://live.douyin.com/webcast/room/web/enter/?web_rid={roomId}&aid=6383&device_platform=web";
                var resp = await _httpClient.GetStringAsync(apiUrl);
                
                try 
                {
                    if (!string.IsNullOrWhiteSpace(resp) && (resp.StartsWith("{") || resp.StartsWith("[")))
                    {
                        using var doc = JsonDocument.Parse(resp);
                        var root = doc.RootElement;

                        if (root.GetProperty("status_code").GetInt32() == 0)
                        {
                            var dataArray = root.GetProperty("data").GetProperty("data");
                            if (dataArray.GetArrayLength() > 0)
                            {
                                var room = dataArray[0];
                                int status = room.GetProperty("status").GetInt32();
                                string title = room.GetProperty("title").GetString();
                                string nickname = room.GetProperty("owner").GetProperty("nickname").GetString();

                                if (status == 2)
                                {
                                    var streams = room.GetProperty("stream_url").GetProperty("flv_pull_url");
                                    string url = streams.TryGetProperty("FULL_HD1", out var flv) ? flv.GetString() : streams.GetProperty("HD1").GetString();
                                    return (true, url, title, nickname);
                                }
                            }
                        }
                    }
                } 
                catch { } // Ignore JSON parse errors and continue to fallback

                // 作为备选方案：通过 HTML 解析 RENDER_DATA
                var htmlContent = await _httpClient.GetStringAsync($"https://live.douyin.com/{roomId}");
                var renderDataMatch = System.Text.RegularExpressions.Regex.Match(htmlContent, @"<script id=""RENDER_DATA"" type=""application/json"">(.*?)</script>");
                if (renderDataMatch.Success)
                {
                    string rawJson = System.Uri.UnescapeDataString(renderDataMatch.Groups[1].Value);
                    using var htmlDoc = JsonDocument.Parse(rawJson);
                    
                    try 
                    {
                        var roomState = FindRoomData(htmlDoc.RootElement);
                        if (roomState.HasValue)
                        {
                            var room = roomState.Value.GetProperty("room");
                            int htmlStatus = room.GetProperty("status").GetInt32();
                            string title = room.GetProperty("title").GetString();
                            string nickname = "未知";
                            
                            try { nickname = htmlDoc.RootElement.GetProperty("user").GetProperty("nickname").GetString(); }
                            catch { }

                            if (nickname == "未知")
                            {
                                try { nickname = room.GetProperty("owner").GetProperty("nickname").GetString(); } catch {}
                            }

                            if (htmlStatus == 2)
                            {
                                var streams = room.GetProperty("stream_url").GetProperty("flv_pull_url");
                                string url = streams.TryGetProperty("FULL_HD1", out var flv) ? flv.GetString() : streams.GetProperty("HD1").GetString();
                                return (true, url, title, nickname);
                            }
                        }
                    } 
                    catch (Exception ex) 
                    { 
                        return (false, null, "RENDER解析出错: " + ex.Message, "未知"); 
                    }
                }

                // 作为最后的备选方案：纯正则提取
                var fallbackMatch = System.Text.RegularExpressions.Regex.Match(htmlContent, @"https?://[^\s""\\]+?\.flv[^\s""\\]*");
                if (fallbackMatch.Success)
                {
                    string url = fallbackMatch.Value.Replace("\\/", "/").Replace("&amp;", "&").Split("\\\"")[0];
                    return (true, url, "通用正则捕获", "未知");
                }
                
                return (false, null, "网页全部解析失败(可能被风控/跳转验证码/或者网页没有流)", "未知");
            }
            catch (Exception ex)
            {
                return (false, null, $"异常: {ex.Message}", "未知");
            }
        }

        private JsonElement? FindRoomData(JsonElement obj)
        {
            if (obj.ValueKind != JsonValueKind.Object) return null;

            if (obj.TryGetProperty("roomInfo", out JsonElement roomInfo))
            {
                return roomInfo;
            }

            foreach (var prop in obj.EnumerateObject())
            {
                if (prop.Name == "roomInfo") return prop.Value;
                
                if (prop.Value.ValueKind == JsonValueKind.Object)
                {
                    var res = FindRoomData(prop.Value);
                    if (res != null) return res;
                }
            }
            return null;
        }
    }
}
