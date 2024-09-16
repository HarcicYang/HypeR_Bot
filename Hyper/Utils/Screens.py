import random


def rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    return r, g, b


def color_txt(text: str, color: tuple[int, int, int]) -> str:
    r = color[0]
    g = color[1]
    b = color[2]
    return f"\x1b[38;2;{r};{g};{b}m{text}\x1b[0m"


start_up = [
    rf"""
    {color_txt('    _______   ________  ________  ________   _______ ', rgb(114, 220, 230))} {color_txt('     _______  ________  ________', rgb(93, 226, 162))} 
    {color_txt('  /    /   / V    /   V         V         V/       R ', rgb(114, 220, 230))} {color_txt('  //      / /         V        A', rgb(93, 226, 162))}
    {color_txt(' /        //         /         /         //        / ', rgb(114, 220, 230))} {color_txt(' //        V         /        _/', rgb(93, 226, 162))}
    {color_txt('/         /A__      /       __/        _/        _/  ', rgb(114, 220, 230))} {color_txt('/         /         //       /  ', rgb(93, 226, 162))}
    {color_txt('A___/____/   A_____A ______/ A________ A____/___/    ', rgb(114, 220, 230))} {color_txt('A________/A________/ A______/   ', rgb(93, 226, 162))} 

    """,

    rf"""
    {color_txt('██╗   ██╗██╗    ██╗██████╗', rgb(114, 220, 230))} {color_txt('███████╗██████╗ ', rgb(91, 223, 201))}   {color_txt('██████╗  ██████╗ ████████╗', rgb(93, 226, 162))}
    {color_txt('██║   ██║╚██╗ ██╔╝██╔══██╗', rgb(114, 220, 230))} {color_txt('██╔════╝██╔══██╗', rgb(91, 223, 201))}   {color_txt('██╔══██╗██╔═══██╗╚══██╔══╝', rgb(93, 226, 162))} 
    {color_txt('████████║ ╚████╔╝ ██████╔╝', rgb(114, 220, 230))} {color_txt('█████╗  ██████╔╝', rgb(91, 223, 201))}   {color_txt('██████╔╝██║   ██║   ██║   ', rgb(93, 226, 162))} 
    {color_txt('██╔═══██║  ╚██╔╝  ██╔═══╝ ', rgb(114, 220, 230))} {color_txt('██╔══╝  ██╔══██╗', rgb(91, 223, 201))}   {color_txt('██╔══██╗██║   ██║   ██║   ', rgb(93, 226, 162))} 
    {color_txt('██║   ██║   ██║   ██║     ', rgb(114, 220, 230))} {color_txt('███████╗██║  ██║', rgb(91, 223, 201))}   {color_txt('██████╔╝╚██████╔╝   ██║   ', rgb(93, 226, 162))} 
    {color_txt('╚═╝   ╚═╝   ╚═╝   ╚═╝     ', rgb(114, 220, 230))} {color_txt('╚══════╝╚═╝  ╚═╝', rgb(91, 223, 201))}   {color_txt('╚═════╝  ╚═════╝    ╚═╝   ', rgb(93, 226, 162))} 

    """,

    rf"""
    {color_txt("HHH  HHH YYY   YY PPPPPPPp,   ,dEPPPP   ,dbPPPp   dBBPPPo OOOOOOOO TTTTTTTTT ", rgb(100, 184, 236))}
    {color_txt("HHHHHHHH YYYoooYY PPPP    p   dEEooo    dRRooP'   BBBoooB OOO  OOO    'TTd   ", rgb(146, 214, 235))}
    {color_txt("HHP  HHH       YY PPPPPPPP' ,EE'      ,RR' P'     BBB   B OOO  OOO   'TTT    ", rgb(91, 223, 205))}
    {color_txt("HHP  HHH PPPPPPYP 888P      EEbdPPP   RR  do      BBBPPPP OOOooOOO 'TTp      ", rgb(93, 226, 158))}                                              

    """,

    rf"""
    {color_txt('M""MMMMM""MM', rgb(92, 225, 178))} {color_txt("                          ", rgb(124, 200, 235))} {color_txt('MM````````MM    M#``````` M ', rgb(104, 255, 211))} {color_txt("           dP  ", rgb(92, 221, 230))} 
    {color_txt('M  MMMMM  MM', rgb(92, 225, 178))} {color_txt("                          ", rgb(124, 200, 235))} {color_txt('MM  mmmm,  M    ##  mmmm. `M', rgb(104, 255, 211))} {color_txt("           88  ", rgb(92, 221, 230))} 
    {color_txt('M         `M', rgb(92, 225, 178))} {color_txt("dP    dP 88d888b. .d8888b.", rgb(124, 200, 235))} {color_txt("M'        .M    #'        .M", rgb(104, 255, 211))} {color_txt(".d8888b. d8888P", rgb(92, 221, 230))} 
    {color_txt('M  MMMMM  MM', rgb(92, 225, 178))} {color_txt("88    88 88'  `88 88ooood8", rgb(124, 200, 235))} {color_txt('MM  MMMb. "M    M#  MMMb.`YM', rgb(104, 255, 211))} {color_txt("88'  `88   88  ", rgb(92, 221, 230))} 
    {color_txt('M  MMMMM  MM', rgb(92, 225, 178))} {color_txt("88.  .88 88.  .88 88.  ...", rgb(124, 200, 235))} {color_txt('MM  MMMMM  M    M#  MMMM`  M', rgb(104, 255, 211))} {color_txt("88.  .88   88  ", rgb(92, 221, 230))} 
    {color_txt('M  MMMMM  MM', rgb(92, 225, 178))} {color_txt("`8888P88 88Y888P' `88888P'", rgb(124, 200, 235))} {color_txt('MM  MMMMM  M    M#       .;M', rgb(104, 255, 211))} {color_txt("`88888P'   dP  ", rgb(92, 221, 230))} 
    {color_txt('MMMMMMMMMMMM', rgb(92, 225, 178))} {color_txt("     .88 88               ", rgb(124, 200, 235))} {color_txt('MMMMMMMMMMMM    M#########M ', rgb(104, 255, 211))} {color_txt("               ", rgb(92, 221, 230))} 
                 {color_txt(" d8888P  dP               ", rgb(124, 200, 235))}   

    """,

    rf"""
     {color_txt("    dBP dBP dBP dBP dBBBBBb  dBBBP dBBBBBb ", rgb(100, 184, 236))}   {color_txt("   dBBBBb   dBBBBP dBBBBBBP", rgb(93, 226, 163))}
     {color_txt("               dBP      dB'            dBP ", rgb(127, 202, 235))}   {color_txt("      dBP  dBP.BP          ", rgb(146, 214, 235))}
     {color_txt("  dBBBBBP     dBP   dBBBP' dBBP    dBBBBK' ", rgb(91, 223, 205))}   {color_txt("  dBBBK'  dBP.BP    dBP    ", rgb(93, 226, 163))}
     {color_txt(" dBP dBP     dBP   dBP    dBP     dBP  BB  ", rgb(127, 202, 235))}   {color_txt(" dB' db  dBP.BP    dBP     ", rgb(93, 226, 158))}
     {color_txt("dBP dBP     dBP   dBP    dBBBBP  dBP  dB'  ", rgb(91, 222, 224))}   {color_txt("dBBBBP' dBBBBP    dBP      ", rgb(93, 226, 163))}

    """
]


def play_startup():
    sc = random.choice(start_up)
    print(sc)


def play_info(version: str):
    print(f"    HypeR Bot 版本 {version}, 正在启动...\n    View at: https://github.com/HarcicYang/HypeR_Bot\n")
