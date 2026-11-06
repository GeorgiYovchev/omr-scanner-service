using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace OmrScanner
{
    static class Sdk
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern bool SetDllDirectory(string lpPathName);
        [DllImport("kernel32.dll")] public static extern uint SetErrorMode(uint uMode);

        const string D = "LScannerSDK.dll";
        [DllImport(D, CharSet = CharSet.Ansi)] public static extern int SInit(string baseDir, IntPtr cb, IntPtr ud);
        [DllImport(D)] public static extern bool SStart();
        [DllImport(D)] public static extern bool SStop();
        [DllImport(D)] public static extern int SGetTicketInfo(byte[] buf, int len);
        [DllImport(D)] public static extern bool SRollBack();
        [DllImport(D)] public static extern bool SGetOriginImageSize(out int w, out int h, out int sz);
        [DllImport(D)] public static extern int SGetOriginImage(byte[] buf, int len);
    }

    // Number-layout mapping, ported from the GENLOT util.c scara tables + genlot_map.py.
    static class Map
    {
        const int ROWS = 22, COLS = 16;
        // scara[row][col] = block*100 + number (0 = separator/empty)
        static readonly int[][] S42 = {
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,101,102,103,104,105,106,107,0,201,202,203,204,205,206,207},
            new[]{0,108,109,110,111,112,113,114,0,208,209,210,211,212,213,214},
            new[]{0,115,116,117,118,119,120,121,0,215,216,217,218,219,220,221},
            new[]{0,122,123,124,125,126,127,128,0,222,223,224,225,226,227,228},
            new[]{0,129,130,131,132,133,134,135,0,229,230,231,232,233,234,235},
            new[]{0,136,137,138,139,140,141,142,0,236,237,238,239,240,241,242},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,301,302,303,304,305,306,307,0,401,402,403,404,405,406,407},
            new[]{0,308,309,310,311,312,313,314,0,408,409,410,411,412,413,414},
            new[]{0,315,316,317,318,319,320,321,0,415,416,417,418,419,420,421},
            new[]{0,322,323,324,325,326,327,328,0,422,423,424,425,426,427,428},
            new[]{0,329,330,331,332,333,334,335,0,429,430,431,432,433,434,435},
            new[]{0,336,337,338,339,340,341,342,0,436,437,438,439,440,441,442},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,501,502,503,504,505,506,507,0,0,0,0,0,0,0,0},
            new[]{0,508,509,510,511,512,513,514,0,0,0,601,602,603,604,605},
            new[]{0,515,516,517,518,519,520,521,0,0,0,701,702,703,704,705},
            new[]{0,522,523,524,525,526,527,528,0,0,0,0,0,0,0,0},
            new[]{0,529,530,531,532,533,534,535,0,0,0,0,802,803,804,805},
            new[]{0,536,537,538,539,540,541,542,0,0,0,906,907,908,909,910},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
        };
        static readonly int[][] S35 = {
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,0,101,102,103,104,105,106,0,0,201,202,203,204,205,206},
            new[]{0,0,107,108,109,110,111,112,0,0,207,208,209,210,211,212},
            new[]{0,0,113,114,115,116,117,118,0,0,213,214,215,216,217,218},
            new[]{0,0,119,120,121,122,123,124,0,0,219,220,221,222,223,224},
            new[]{0,0,125,126,127,128,129,130,0,0,225,226,227,228,229,230},
            new[]{0,0,131,132,133,134,135,0,0,0,231,232,233,234,235,0},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,0,301,302,303,304,305,306,0,0,401,402,403,404,405,406},
            new[]{0,0,307,308,309,310,311,312,0,0,407,408,409,410,411,412},
            new[]{0,0,313,314,315,316,317,318,0,0,413,414,415,416,417,418},
            new[]{0,0,319,320,321,322,323,324,0,0,419,420,421,422,423,424},
            new[]{0,0,325,326,327,328,329,330,0,0,425,426,427,428,429,430},
            new[]{0,0,331,332,333,334,335,0,0,0,431,432,433,434,435,0},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
            new[]{0,0,501,502,503,504,505,506,0,0,0,0,0,0,0,0},
            new[]{0,0,507,508,509,510,511,512,0,0,0,0,0,0,0,0},
            new[]{0,0,513,514,515,516,517,518,0,0,602,603,604,605,606,0},
            new[]{0,0,519,520,521,522,523,524,0,0,707,708,709,710,0,0},
            new[]{0,0,525,526,527,528,529,530,0,0,0,0,0,0,0,0},
            new[]{0,0,531,532,533,534,535,0,0,0,0,0,0,0,0,0},
            new[]{0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},
        };

        static int Mirror(int c)
        {
            if (c >= 1 && c <= 7) return 8 - c;       // mirror within left 7-col block
            if (c >= 9 && c <= 15) return 24 - c;     // mirror within right 7-col block
            return c;
        }

        static bool[][] DecodeMatrix(byte[] raw)
        {
            var t = new bool[ROWS][];
            for (int r = 0; r < ROWS; r++) t[r] = new bool[COLS];
            for (int i = 0; i < 44; i += 2)
            {
                int n = (raw[7 + i] << 8) | raw[7 + i + 1];   // big-endian row word
                for (int j = 15; j >= 0; j--)
                    if (((n >> j) & 1) != 0) t[i / 2][15 - j] = true;
            }
            return t;
        }

        static int DetectType(bool[][] t)
        {
            // type-42 row0 signature = cols {0,7,9,10,13}
            var want = new HashSet<int> { 0, 7, 9, 10, 13 };
            var got = new HashSet<int>();
            for (int c = 0; c < COLS; c++) if (t[0][c]) got.Add(c);
            if (got.SetEquals(want)) return 42;
            return 42; // default 42 until a 35 signature is known
        }

        // -> {"type":N,"blocks":[[...]x5],"draws":[...]}
        public static string ToJson(byte[] raw)
        {
            var t = DecodeMatrix(raw);
            int type = DetectType(t);
            int[][] scara = (type == 35) ? S35 : S42;
            var blk = new Dictionary<int, List<int>>();
            for (int r = 0; r < ROWS; r++)
                for (int c = 0; c < COLS; c++)
                    if (t[r][c])
                    {
                        int val = scara[r][Mirror(c)];
                        if (val != 0)
                        {
                            int b = val / 100, v = val % 100;
                            if (!blk.ContainsKey(b)) blk[b] = new List<int>();
                            blk[b].Add(v);
                        }
                    }
            foreach (var k in blk.Keys) blk[k].Sort();

            var sb = new StringBuilder();
            sb.Append("{\"type\":").Append(type).Append(",\"blocks\":[");
            for (int b = 1; b <= 5; b++)
            {
                if (b > 1) sb.Append(',');
                sb.Append('[');
                if (blk.TryGetValue(b, out var l))
                    for (int i = 0; i < l.Count; i++) { if (i > 0) sb.Append(','); sb.Append(l[i]); }
                sb.Append(']');
            }
            sb.Append("],\"draws\":[");
            int[] drawBlocks = (type == 42) ? new[] { 8, 9 } : new[] { 6, 7, 8, 9 };
            bool first = true;
            foreach (int b in drawBlocks)
                if (blk.TryGetValue(b, out var l))
                    foreach (int v in l) { if (!first) sb.Append(','); sb.Append(v); first = false; }
            sb.Append("]}");
            return sb.ToString();
        }
    }

    static class Program
    {
        static volatile bool busy = false;
        static bool had = false;
        static System.Windows.Forms.Timer timer;

        static void Log(string s) { Console.WriteLine(s); Console.Out.Flush(); }

        [STAThread]
        static void Main(string[] args)
        {
            string lib64 = args.Length > 0 ? args[0] : @"C:\Repos\gitlab\OMR\lib64";
            Sdk.SetDllDirectory(lib64);
            Sdk.SetDllDirectory(Path.Combine(lib64, "lib"));
            Sdk.SetDllDirectory(lib64);                       // keep lib64 as primary
            Sdk.SetErrorMode(0x0001 | 0x0002 | 0x8000);

            int rc = Sdk.SInit(Path.Combine(lib64, "bin"), IntPtr.Zero, IntPtr.Zero);
            Log("SInit " + rc);
            if (rc != 0) { Log("SInit FAILED, exiting"); return; }
            Log("SStart " + Sdk.SStart());
            Log("READY");

            timer = new System.Windows.Forms.Timer { Interval = 60 };
            timer.Tick += Tick;
            timer.Start();
            Application.Run();                                // real STA message loop
        }

        static bool HasData(byte[] b)
        {
            for (int i = 7; i < 51 && i < b.Length; i++) if (b[i] != 0) return true;
            return false;
        }

        static void Tick(object s, EventArgs e)
        {
            if (busy) return;
            byte[] buf = new byte[65536];
            int rc = Sdk.SGetTicketInfo(buf, buf.Length);
            bool has = rc > 1 && rc < 65536 && HasData(buf);
            if (has && !had)
            {
                had = true;
                busy = true;
                Log("RESULT " + Map.ToJson(buf));
                // Eject on a background thread so THIS (UI) thread keeps pumping
                // messages while SRollBack runs — that is what lets it complete.
                Task.Run(() =>
                {
                    try
                    {
                        if (Sdk.SGetOriginImageSize(out int w, out int h, out int sz))
                        {
                            int m = Math.Max(w, Math.Max(h, sz));
                            if (m > 0 && m < 8 * 1024 * 1024) Sdk.SGetOriginImage(new byte[m + 16], m);
                        }
                    }
                    catch { }
                    try { Sdk.SRollBack(); } catch { }
                    Thread.Sleep(300);
                    busy = false;
                });
            }
            else if (!has)
            {
                had = false;
            }
        }
    }
}
