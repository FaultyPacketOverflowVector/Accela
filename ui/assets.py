DEPOT_BLACKLIST = [
    228981,
    228982,
    228983,
    228984,
    228985,
    228986,
    228987,
    228988,
    228989,
    229000,
    229001,
    229002,
    229003,
    229004,
    229005,
    229006,
    229007,
    229010,
    229011,
    229012,
    229020,
    229030,
    229031,
    229032,
    229033,
    228990,
    239142,
    798541,
    798542,
    798543,
    1034630,
]

MINIMIZE = r"""
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <path d="M6 11H18V13H6V11Z" fill="#000000" style="--darkreader-inline-fill: var(--darkreader-background-000000, #000000);" data-darkreader-inline-fill=""></path> </g></svg>
"""

MAXIMIZE = r"""
<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <path d="M4.5 3C3.67157 3 3 3.67157 3 4.5V11.5C3 12.3284 3.67157 13 4.5 13H11.5C12.3284 13 13 12.3284 13 11.5V4.5C13 3.67157 12.3284 3 11.5 3H4.5ZM4.5 4H11.5C11.7761 4 12 4.22386 12 4.5V11.5C12 11.7761 11.7761 12 11.5 12H4.5C4.22386 12 4 11.7761 4 11.5V4.5C4 4.22386 4.22386 4 4.5 4Z" fill="#212121" style="--darkreader-inline-fill: var(--darkreader-background-212121, #191b1c);" data-darkreader-inline-fill=""></path> </g></svg>
"""

CLOSE = r"""
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <path d="M18 6L6 18" stroke="#33363F" stroke-width="2" stroke-linecap="square" stroke-linejoin="round" style="--darkreader-inline-stroke: var(--darkreader-text-33363f, #c4bfb7);" data-darkreader-inline-stroke=""></path> <path d="M6 6L18 18" stroke="#33363F" stroke-width="2" stroke-linecap="square" stroke-linejoin="round" style="--darkreader-inline-stroke: var(--darkreader-text-33363f, #c4bfb7);" data-darkreader-inline-stroke=""></path> </g></svg>
"""

POWER_SVG = r"""
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
  <line x1="12" y1="2" x2="12" y2="12"></line>
</svg>
"""

AUDIO_SVG = r"""
<svg viewBox="0 -1.5 31 31" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:sketch="http://www.bohemiancoding.com/sketch/ns" fill="#000000" style="--darkreader-inline-fill: var(--darkreader-background-000000, #000000);" data-darkreader-inline-fill=""><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <title>volume-full</title> <desc>Created with Sketch Beta.</desc> <defs> </defs> <g id="Page-1" stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" sketch:type="MSPage" style="--darkreader-inline-stroke: none;" data-darkreader-inline-stroke=""> <g id="Icon-Set-Filled" sketch:type="MSLayerGroup" transform="translate(-258.000000, -571.000000)" fill="#000000" style="--darkreader-inline-fill: var(--darkreader-background-000000, #000000);" data-darkreader-inline-fill=""> <path d="M277,571.015 L277,573.068 C282.872,574.199 287,578.988 287,585 C287,590.978 283,595.609 277,596.932 L277,598.986 C283.776,597.994 289,592.143 289,585 C289,577.857 283.776,572.006 277,571.015 L277,571.015 Z M272,573 L265,577.667 L265,592.333 L272,597 C273.104,597 274,596.104 274,595 L274,575 C274,573.896 273.104,573 272,573 L272,573 Z M283,585 C283,581.477 280.388,578.59 277,578.101 L277,580.101 C279.282,580.564 281,582.581 281,585 C281,587.419 279.282,589.436 277,589.899 L277,591.899 C280.388,591.41 283,588.523 283,585 L283,585 Z M258,581 L258,589 C258,590.104 258.896,591 260,591 L263,591 L263,579 L260,579 C258.896,579 258,579.896 258,581 L258,581 Z" id="volume-full" sketch:type="MSShapeGroup"> </path> </g> </g> </g></svg>
"""

GEAR_SVG = r"""
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20.94c-4.94 0-8.94-4-8.94-8.94S7.06 3.06 12 3.06s8.94 4 8.94 8.94-4 8.94-8.94 8.94z"></path>
  <path d="M12 15.94c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4z"></path>
  <path d="M12 3.06L12 1"></path>
  <path d="M12 23L12 20.94"></path>
  <path d="M4.22 4.22L5.64 5.64"></path>
  <path d="M18.36 18.36L19.78 19.78"></path>
  <path d="M1 12L3.06 12"></path>
  <path d="M20.94 12L23 12"></path>
  <path d="M4.22 19.78L5.64 18.36"></path>
  <path d="M18.36 5.64L19.78 4.22"></path>
</svg>
"""

SEARCH_SVG = r"""
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="8"></circle>
  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
</svg>
"""

PALETTE_SVG = r"""
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="13.5" cy="6.5" r=".5"></circle>
  <circle cx="17.5" cy="10.5" r=".5"></circle>
  <circle cx="8.5" cy="7.5" r=".5"></circle>
  <circle cx="6.5" cy="12.5" r=".5"></circle>
  <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"></path>
</svg>
"""

BOOK_SVG = r"""
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
</svg>
"""

"""
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                            @@@@@@                                                                    
                                                                         @@@@@@@@@@@                                                                  
                                                                        @@@@@@@@@@@@@                                                                 
                                                                        @@@@@@@@@@@@@                                                                 
                                                                        @@@@@@ @@@@@@                                                                 
                                                                 @@@@@@@@@@@@@@@@@@@@@@@@@                                                            
                                                            @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                                                       
                                                         @@@@@@@@@        @@@@@@@@@@     @@@@@@@@@@                                                   
                                                      @@@@@@@                @@@@             @@@@@@@@                                                
                                                   @@@@@@@                                       @@@@@@@                                              
                                                 @@@@@@                   @@@@@@@                   @@@@@@                                            
                                               @@@@@@              @@@@@@@@@@@@@@@@@@@@@               @@@@@                                          
                                             @@@@@             @@@@@@@@@    @@@    @@@@@@@@@@            @@@@@                                        
                                           @@@@@@           @@@@@@ @@@@@@@@@@@@@@@@@@@@@ @@@@@@           @@@@@@                                      
                                         @@@@@@@@@@      @@@@@ @@@@@@@@@@@@@@@@@@@@@@@@@@@@@ @@@@@     @@@@@@@@@@                                     
                                      @@@@@@@@@@@@@    @@@@ @@@@@@@@@@               @@@@@@@@@@ @@@@  @@@@@@@@@@@@@                                   
                                    @@@@@@@@@  @@@@   @@@ @@@@@@@@       @@@@@@@@@        @@@@@@@ @@@ @@@@   @@@@@@@@@                                
                                 @@@@@@@@@  @@@@@@@ @@@ @@@@@@@    @@@@@@@@@@@@@@@@@@@@@    @@@@@@@ @@@@@@@@@@  @@@@@@@@@                             
                             @@@@@@@@@@@ @@@@@@@@@ @@@ @@@@@@   @@@@@@@@@@@@@@@@@@@@@@@@@@@   @@@@@@ @@@@@@@@@@@@ @@@@@@@@@@                          
                           @@@@@@@@@@ @@@@@@@@@   @@@ @@@@@   @@@@@@@@   @       @    @@@@@@@   @@@@@@@@@  @@@@@@@@ @@@@@@@@@@                        
                           @@@@@@@@ @@@@@@@@     @@@ @@@@@   @@@@@@     @@@@@@@@@@@@     @@@@@    @@@@@@@@    @@@@@@@  @@@@@@@@                       
                          @@@@@@@ @@@@@@@@      @@@ @@@@   @@@@@     @@@@@ @@@@@ @@@@@@    @@@@@   @@@@ @@@     @@@@@@@@ @@@@@@@                      
                         @@@@@@ @@@@@@@         @@ @@@@   @@@@@    @@@@@@@@@@@@@@@@@ @@@@   @@@@@   @@@@ @@@       @@@@@@  @@@@@@                     
                        @@@@@  @@@@@@@         @@@@@@@    @@@@   @@@@@@@@@@@@@@@@@@@@@ @@@   @@@@    @@@@ @@         @@@@@  @@@@@@                    
                       @@@@@   @@@@ @@         @@ @@@@   @@@@   @@@ @@@@@@@@@@@@@@@@@@@ @@@   @@@@   @@@@ @@         @ @@@@  @@@@@@                   
                      @@@@@   @@@@@ @@         @@ @@@    @@@    @@ @@@@@@@@@@@@@@@@@@@@@ @@    @@@    @@@@@@         @@ @@@@   @@@@@                  
                      @@@@@   @@@@  @@         @ @@@@    @@@    @@@@@@@@@@@     @@@@@@@@@@@@   @@@    @@@@ @@         @ @@@@   @@@@@                  
                      @@@@   @@@@   @@        @@ @@@@   @@@@   @@@@@@@@@@@        @@@@@@@ @@   @@@    @@@@ @@         @ @@@@    @@@@                  
                      @@@@    @@@@  @@        @@ @@@@   @@@@   @@@@@@@@@@         @@@@@@@ @@   @@@@   @@@@ @@         @ @@@@   @@@@@                  
                      @@@@@   @@@@@ @@         @@@@@@    @@@    @@ @@@@@@@       @@@@@@@@@@    @@@    @@@@ @@        @@@@@@   @@@@@@                  
                      @@@@@@@  @@@@@@@         @@ @@@    @@@    @@@@@@@@@@@@@@@@@@@@@@@@ @@    @@@    @@@@@@         @@@@@@ @@@@@@@                   
                        @@@@@@@ @@@@@@@        @@ @@@@   @@@@ @  @@ @@@@@@@@@@@@@@@@@@@ @@    @@@@   @@@@ @@       @@@@@@  @@@@@@@                    
                        @@@@@@@@@ @@@@@@@@    @@ @@@@    @@@@ @  @@@ @@@@@@@@@@@@@@@@@@@  @ @@@@   @@@@@@@@    @@@@@@@@ @@@@@@@@                     
                        @@@@@@@@@@@ @@@@@@@@    @@ @@@@    @@@@    @@@@ @@@@@@@@@@@ @@@@    @@@@    @@@@ @@   @@@@@@@  @@@@@@@@@                      
                            @@@@@@@@   @@@@@@@@ @@@ @@@@    @@@@@    @@@@@@@   @@@@@@@    @@@@@    @@@@ @@@@@@@@@@@  @@@@@@@@                         
                              @@@@@@@@@  @@@@@@@@@@@ @@@@    @@@@@@      @@@@@@@@@@     @@@@@@    @@@@ @@@@@@@@@@  @@@@@@@@                           
                                 @@@@@@@@   @@@@@@@@@ @@@@@   @@@@@@@@    @@@@@@@    @@@@@@@@   @@@@@ @@@@@@@@   @@@@@@@@                             
                                    @@@@@@@@  @@@@@@@@ @@@@@@    @@@@@@@@@@@   @@@@@@@@@@@@   @@@@@@ @@@@@@   @@@@@@@@                                
                              @@@@@@@@ @@@@@@@@@@@@  @@@ @@@@@@     @@@@@@@@@ @@@@@@@@@@    @@@@@@ @@@ @@@@@@@@@@@@  @@@@@@@@                         
                             @@@@@@@@@@@ @@@@@@@@@     @@@@@@@@@@@       @@@@ @@@@       @@@@@@@@ @@   @@@@@@@@@@@ @@@@@@@@@@@                        
                            @@@@@@@@@@@@@@@@@@@@@       @@@@ @@@@@@@@    @@@@ @@@     @@@@@@@@@ @@@      @@@@@@@@@@@@@@@@@@@@@@                       
                            @@@@@@  @@@@@@@@@@@@           @@@@ @@@@@@    @@@ @@@    @@@@@@@@@@@@          @@@@@@@@@@@@  @@@@@@                       
                            @@@@@@@@@@@@@@  @@@@@            @@@@@@@@@    @@@ @@@    @@@@@@@@@            @@@@@  @@@@@@@@@@@@@@                       
                             @@@@@@@@@@@@     @@@@@             @@@@@@@@@@@@@@@@@@@@@@@@@@@@             @@@@     @@@@@@@@@@@@                        
                              @@@@@@@@@@        @@@@@              @@@@@@@@@@@@@@@@@@@@@@              @@@@        @@@@@@@@@@                         
                                @@@@@@            @@@@@            @@@    @@@ @@@    @@@@           @@@@@            @@@@@                            
                                              @@@@@@ @@@@@         @@@    @@@ @@@    @@@@        @@@@@ @@@@@@                                         
                                             @@@@@@@@@ @@@@@@@    @@@    @@@@  @@@   @@@@    @@@@@@@ @@@@@@@@@                                        
                                            @@@@@@@@@@@   @@@@@@@@@@@    @@@@  @@@   @@@@@@@@@@@@  @@@@@@@@@@@@                                       
                                            @@@@   @@@@@@@    @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@    @@@@@@@   @@@@                                       
                                            @@@@@    @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@    @@@@@                                       
                                             @@@@@@    @@@@@@@@@@@@@   @@@@@@  @@@@@   @@@@@@@@@@@@@    @@@@@@                                        
                                              @@@@@@@      @@@@@@     @@@@@@    @@@@@     @@@@@@      @@@@@@@                                         
                                                @@@@@@@@@          @@@@@@@       @@@@@@@          @@@@@@@@@                                           
                                                  @@@@@@@@@@@@@@@@@@@@@@@         @@@@@@@@@@@@@@@@@@@@@@@@                                            
                                                     @@@@@@@@@@@@@@@@@@             @@@@@@@@@@@@@@@@@@@                                               
                                                         @@@@@@@@@@@                    @@@@@@@@@@                                                    
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
                                                                                                                                                      
"""
